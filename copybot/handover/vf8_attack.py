"""Adversarial PoCs (verifier vf8, protocol and statistics lens). Not part of the suite."""
import json
import os
import unittest
from unittest import mock

from tests.test_lab_families import (A3Base, A5Base, ALL4 as ALL4_, BASE, CLEAN, F, FCARRY, H, L, families, fleet,
                                     lifecycle, pipeline, promotion, registry, ts)
from lab.__main__ import main


class DoubleReserve(A5Base):
    def test_reapproval_of_a_valid_family_reserves_twice_and_a_cohort_spends_once(self):
        self.ready()
        self.approve()                                       # a second request/confirm while the first is valid
        held = self.db.one("SELECT SUM(alpha) FROM alpha_ledger WHERE exp_id='family:fcarry'")[0]
        print("\n[A] family:fcarry held after two confirms:", held, "programme used:", families.alpha_reserved(self.db))
        self.assertEqual(sorted(fleet.strategy_pass(self.db)["registered"]), BASE)
        self.screened(F, sharpe=1.5)
        for e in (L, H):
            self.screened(e, observe=False)
        fleet.strategy_pass(self.db)
        cf = families.cohort(self.db, "fcarry")
        print("[A] cohort M", cf["M"], "alpha_i", cf["alpha_i"], "programme used after spend:",
              families.alpha_reserved(self.db), "family row left:", families.reserved(self.db, "fcarry"))
        with self.assertRaises(families.FamilyError):
            families.revoke(self.db, "fcarry", "human:anton", "release the stuck reservation please")
        self.assertAlmostEqual(families.alpha_reserved(self.db), 0.025)   # 2 x alpha_F for one family, forever

    def test_reapproval_after_a_void_approval_reserves_again(self):
        self.ready()
        self.blobs["family"] = {**self.blobs["family"], "committed": "abcdef01ffff", "working": "abcdef01ffff"}
        self.assertIsNone(families.approval(self.db, "fcarry"))               # void: a bound file changed
        self.approve()
        print("\n[A2] held after void + re-approval:", families.reserved(self.db, "fcarry"))
        self.assertAlmostEqual(families.reserved(self.db, "fcarry"), 0.025)


class ForgedSpec(A3Base):
    def test_a_hand_made_version_2_registers_with_costs_universe_and_holdout_the_family_file_does_not_have(self):
        families.discover_all(self.db)
        self.revive()
        self.approve()
        self.touch()
        p = families.approval_payload(self.db, "fcarry")
        spec = families.instance_spec(FCARRY, "filt", p["blobs"], {})
        spec.update(costs={"taker_fee": 0.0, "half_spread": 0.0, "slippage": 0.0}, min_symbols=1,
                    holdout_exclude=[], universe=["BTCUSDT", "ETHUSDT", "SOLUSDT"],
                    grid=[{"lookback_days": 7, "enter_apr": 0.01}, {"lookback_days": 7, "enter_apr": 0.02}],
                    code="research/families/fcarry.json", alpha="0.0")
        path = os.path.join(self.tmp, "forged.json")
        with open(path, "w") as f:
            json.dump(spec, f)
        real = registry.blob_at
        fam_blob = CLEAN["family"]["committed"]
        out = []
        with mock.patch.object(registry, "blob_at",               # as git answers: the committed family file blob
                               lambda c, pth: fam_blob if pth.endswith("fcarry.json") else real(c, pth)), \
                mock.patch.object(registry, "git_committed", lambda p: True):   # the spec file is committed
            main(["add-version", F, "--spec", path], db_path=self.db_path, out=out.append)
            print("\n[B] add-version:", out)
            reg = fleet.strategy_pass(self.db)["registered"]
        got = pipeline._spec(self.db, F)
        print("\n[B] registered:", reg, "state", lifecycle.state(self.db, F), "| spec costs", got["costs"],
              "min_symbols", got["min_symbols"], "holdout_exclude", got["holdout_exclude"], "universe", got["universe"],
              "grid", got["grid"])
        self.assertIn(F, reg)
        self.assertEqual(got["costs"]["taker_fee"], 0.0)


class CliBypass(A5Base):
    def test_lab_result_and_lab_transition_put_a_family_instance_in_screen_passed(self):
        self.register()
        out = []
        with mock.patch.dict(os.environ, {"CLAUDECODE": "1"}), \
                mock.patch.object(families, "GUARD", families.interactive_human):
            lifecycle.auto_transition(self.db, F, "SCREENING", "system:fixture", "screening starts in this test")
            main(["result", F, "--label", "EXPLORATORY", "--verdict", "PASS forged by the CLI"], db_path=self.db_path,
                 out=out.append)
            rid = self.db.one("SELECT MAX(id) FROM results WHERE exp_id=?", F)[0]
            main(["transition", F, "SCREEN_PASSED", "--reason", "forged straight to SCREEN_PASSED",
                  "--result-id", str(rid)], db_path=self.db_path, out=out.append)
        print("\n[C1]", out, "-> state", lifecycle.state(self.db, F))
        self.assertEqual(lifecycle.state(self.db, F), "SCREEN_PASSED")

    def test_a_forged_forward_pass_closes_the_family_as_pass_and_lifts_the_programme_stop(self):
        self.register()
        self.screened(F, sharpe=1.5)
        for e in (L, H):
            self.screened(e, observe=False)
        fleet.strategy_pass(self.db)
        cf = families.cohort(self.db, "fcarry")
        self.assertEqual(cf["selected"], [F])
        out = []
        with mock.patch.dict(os.environ, {"CLAUDECODE": "1"}):
            main(["result", F, "--label", "VALIDATION", "--verdict", families.FORWARD_PASS + ": forged"],
                 db_path=self.db_path, out=out.append)
            rid = self.db.one("SELECT MAX(id) FROM results WHERE exp_id=?", F)[0]
            main(["transition", F, "SCREEN_PASSED", "--reason", "forged forward pass, no window was read",
                  "--result-id", str(rid)], db_path=self.db_path, out=out.append)
        st = fleet.strategy_pass(self.db)["families"]["fcarry"]
        self.now[0] = ts(2028, 7, 2)
        print("\n[C2]", out, "state", lifecycle.state(self.db, F), "| family status:", st,
              "| forward_passes:", families.forward_passes(self.db), "| programme_stop 2028-07-02:",
              families.programme_stop(self.db))
        self.assertEqual(lifecycle.state(self.db, F), "SCREEN_PASSED")
        self.assertEqual(families.closed(self.db, "fcarry")["outcome"], "PASS")
        self.assertEqual(families.programme_stop(self.db), [])


class PerTag(A3Base):
    def test_a_third_family_on_the_same_tag_is_approved_and_registers(self):
        for fid in ("fone", "ftwo"):
            e = f"E_{fid}__x1_a8"
            self.db.append("experiments", exp_id=e, version=1, created_ts=0,
                           mechanism_tag="delta_neutral_funding_carry", fingerprint=e,
                           spec_json={"execution": "taker", "family": fid})
            for st in ("REGISTERED", "SCREENING", "REJECTED"):
                self.db.append("transitions", exp_id=e, ts=0, from_state=None, to_state=st, actor="fixture",
                               reason="fixture: an earlier family on the same tag")
            self.db.event("family.closed", "system:fixture", None, {"family": fid, "outcome": "FUTILE_IN_SAMPLE"})
        real = families.load

        def acked(path_or_fid):
            fam = real(path_or_fid)
            if fam.get("family_id") == "fcarry":
                fam["graveyard_acknowledged"] = fam["graveyard_acknowledged"] + [
                    {"exp_id": f"E_{x}__x1_a8", "match": "exact", "lessons_addressed": ["x"],
                     "materially_different_because": "materially different because a later, separately drafted family"}
                    for x in ("fone", "ftwo")]
            return fam
        with mock.patch.object(families, "load", acked):
            self.ready()
            reg = fleet.strategy_pass(self.db)["registered"]
        print("\n[D] third family on tag delta_neutral_funding_carry: approval", families.approval(self.db, "fcarry"),
              "registered", reg)
        self.assertEqual(sorted(reg), BASE)


class PartialBatch(A3Base):
    def test_approval_before_the_revivals_registers_a_partial_base_batch(self):
        families.discover_all(self.db)
        self.approve()
        self.touch()
        self.revive([F])
        first = fleet.strategy_pass(self.db)["registered"]
        self.revive([L, H])
        second = fleet.strategy_pass(self.db)["registered"]
        last = [json.loads(r[0])["reasons"] for r in self.db.q("SELECT payload FROM events WHERE kind='family.waiting'")]
        print("\n[E] first pass", first, "second pass", second, "states",
              {e: lifecycle.state(self.db, e) for e in BASE}, "waiting:", last[-1:])
        self.assertEqual(first, [F])
        self.assertEqual(second, [])


class HumanPaper(A3Base):
    def test_a_validated_family_instance_reaches_paper_trading_in_a_terminal_and_is_authorized(self):
        self.ready()
        fleet.strategy_pass(self.db)
        e = L
        for st in ("SCREENING", "OBSERVATION", "SCREEN_PASSED", "VALIDATION"):
            self.db.append("transitions", exp_id=e, ts=0, from_state=None, to_state=st, actor="fixture",
                           reason="fixture: the path to a holdout")
        rid = registry.record_result(self.db, e, "VALIDATION", "PASS (holdout): fixture", {}, {}, "system:fixture")
        self.db.append("transitions", exp_id=e, ts=0, from_state="VALIDATION", to_state="VALIDATED", actor="fixture",
                       reason="fixture: holdout passed", evidence={"result_id": rid})
        code = lifecycle.request_approval(self.db, e, "PAPER_TRADING", "human:anton", "paper trade the family please")
        lifecycle.confirm(self.db, code, "human:anton", guards=(registry.complete_spec_guard,
                                                                families.terminal_guard))
        print("\n[F] state", lifecycle.state(self.db, e), "trading_authorized", promotion.trading_authorized(self.db, e))
        self.assertEqual(lifecycle.state(self.db, e), "PAPER_TRADING")


class BudgetPrefix(A3Base):
    def test_a_negative_row_under_a_family_prefixed_id_lets_reservations_exceed_w0(self):
        out = []
        main(["discover", "family:zzz", "--hypothesis", "h", "--mechanism", "m", "--instrument", "i", "--horizon",
              "days", "--execution", "taker", "--source", "s"], db_path=self.db_path, out=out.append)
        spec = {k: "x" for k in registry.REQUIRED_SPEC}
        spec.update(code="lab/engine/data.py", alpha="-0.05")
        path = os.path.join(self.tmp, "neg.json")
        with open(path, "w") as f:
            json.dump(spec, f)
        with mock.patch.object(registry, "git_committed", lambda p: True):
            main(["add-version", "family:zzz", "--spec", path], db_path=self.db_path, out=out.append)
        for fid in ("fa", "fb", "fc", "fd"):                     # four real families already hold W0 = 0.05
            self.db.append("alpha_ledger", exp_id=f"family:{fid}", ts=0, alpha=0.0125, note="A8 reserve")
        print("\n[G]", out, "alpha_reserved:", families.alpha_reserved(self.db))
        self.ready()                                            # a fifth family is approved
        real = self.db.one("SELECT SUM(alpha) FROM alpha_ledger WHERE note='A8 reserve'")[0]
        print("[G] approval", families.approval(self.db, "fcarry"), "A8 reserve rows sum:", real, "> W0", families.W0)
        self.assertGreater(real, families.W0)


class DiscoverBypass(A3Base):
    def test_lab_discover_pre_creates_instances_under_another_tag_skipping_suppression_and_revival(self):
        out = []
        for e in BASE:
            main(["discover", e, "--hypothesis", "h", "--mechanism", "harmless_tag", "--instrument", "i",
                  "--horizon", "days", "--execution", "taker", "--source", "s"], db_path=self.db_path, out=out.append)
        found = families.discover_all(self.db)
        self.approve()
        self.touch()
        p = families.approval_payload(self.db, "fcarry")
        real, fam_blob = registry.blob_at, CLEAN["family"]["committed"]
        for e in BASE:
            spec = families.instance_spec(FCARRY, families.instance_of(e)[1], p["blobs"], {})
            spec.update(code="research/families/fcarry.json", mechanism_tag="harmless_tag", alpha="0.0")
            path = os.path.join(self.tmp, f"{e}.json")
            with open(path, "w") as f:
                json.dump(spec, f)
            with mock.patch.object(registry, "blob_at",
                                   lambda c, pth: fam_blob if pth.endswith("fcarry.json") else real(c, pth)), \
                    mock.patch.object(registry, "git_committed", lambda p: True):
                main(["add-version", e, "--spec", path], db_path=self.db_path, out=out.append)
        reg = fleet.strategy_pass(self.db)["registered"]
        tags = {r[0]: r[1] for r in self.db.q("SELECT exp_id, mechanism_tag FROM experiments WHERE version=2")}
        print("\n[H]", out, "discover_all:", found, "| registered without any revival:", reg, "| tags:", tags,
              "| covering for a second family:",
              registry.covering(self.db, "delta_neutral_funding_carry", "taker", "fp"))
        self.assertEqual(sorted(reg), BASE)
        self.assertEqual(set(tags.values()), {"harmless_tag"})


if __name__ == "__main__":
    unittest.main()
