"""Adversarial PoCs (verifier vf8, protocol and statistics lens), turned around after the fix commit 4c32ff6: every
attack must now be refused, at the guard its finding named. Where it is cheap, a second variant skips the CLI and
writes straight into the registry, so the next guard down (register_transition, trading_authorized, the ledger sums)
is tested too. Not part of the suite. Run from copybot/: PYTHONPATH=. python3 -m unittest handover.vf8_attack"""
import json
import os
import unittest
from unittest import mock

from tests.test_lab_families import (A3Base, A5Base, BASE, CLEAN, F, FCARRY, H, L, families, fleet, lifecycle,
                                     pipeline, promotion, registry, ts)
from lab.__main__ import main


def cli(args, db_path):
    out = []
    main(args, db_path=db_path, out=out.append)
    return out


def refused(out):
    return bool(out) and all(str(x).startswith("refused") for x in out)


def forge(db, eid, label, verdict, metrics, actor):
    """A result row and its event written straight into the registry, the way record_result writes them (record_result
    itself refuses a non-system actor for a family instance)."""
    v = registry.latest(db, eid)
    with db.tx():
        rid = db.append("results", exp_id=eid, version=v["version"], ts=0, label=label, verdict=verdict,
                        metrics=metrics, evidence={}, supersedes=None)
        db.event("result.recorded", actor, eid, {"result_id": rid, "label": label, "verdict": verdict,
                                                 "supersedes": None, "reason": None})
    return rid


class DoubleReserve(A5Base):
    def test_a_second_approval_of_a_valid_family_is_refused_and_the_cohort_spends_exactly_alpha_f(self):
        self.ready()
        with self.assertRaises(families.FamilyError):
            self.approve()                                   # a second request/confirm while the first is valid
        self.assertAlmostEqual(families.reserved(self.db, "fcarry"), 0.0125)
        self.assertEqual(sorted(fleet.strategy_pass(self.db)["registered"]), BASE)
        self.screened(F, sharpe=1.5)
        for e in (L, H):
            self.screened(e, observe=False)
        fleet.strategy_pass(self.db)
        cf = families.cohort(self.db, "fcarry")
        print("\n[A] cohort M", cf["M"], "alpha_i", cf["alpha_i"], "programme used:", families.alpha_reserved(self.db),
              "family row left:", families.reserved(self.db, "fcarry"))
        self.assertAlmostEqual(families.reserved(self.db, "fcarry"), 0.0)
        self.assertAlmostEqual(families.alpha_reserved(self.db), 0.0125)    # exactly alpha_F for one family

    def test_an_excess_reservation_is_released_when_the_cohort_is_fixed(self):
        self.register()
        self.db.append("alpha_ledger", exp_id="family:fcarry", ts=0, alpha=0.0125, note="A8 reserve")   # a stray row
        self.screened(F, sharpe=1.5)
        for e in (L, H):
            self.screened(e, observe=False)
        fleet.strategy_pass(self.db)
        print("\n[A1] after the cohort: family row", families.reserved(self.db, "fcarry"), "programme",
              families.alpha_reserved(self.db))
        self.assertAlmostEqual(families.reserved(self.db, "fcarry"), 0.0)
        self.assertAlmostEqual(families.alpha_reserved(self.db), 0.0125)

    def test_a_reapproval_after_a_void_approval_is_refused_until_a_revoke_releases_the_reservation(self):
        self.ready()
        self.blobs["family"] = {**self.blobs["family"], "committed": "abcdef01ffff", "working": "abcdef01ffff"}
        self.assertIsNone(families.approval(self.db, "fcarry"))               # void: a bound file changed
        with self.assertRaises(families.FamilyError):
            self.approve()
        self.assertAlmostEqual(families.reserved(self.db, "fcarry"), 0.0125)
        families.revoke(self.db, "fcarry", "human:anton", "the family file changed, release and approve again")
        self.assertAlmostEqual(families.reserved(self.db, "fcarry"), 0.0)
        self.approve()
        print("\n[A2] held after void + revoke + re-approval:", families.reserved(self.db, "fcarry"))
        self.assertAlmostEqual(families.reserved(self.db, "fcarry"), 0.0125)


class ForgedSpec(A3Base):
    def forged(self, p):
        spec = families.instance_spec(FCARRY, "filt", p["blobs"], {})
        spec.update(costs={"taker_fee": 0.0, "half_spread": 0.0, "slippage": 0.0}, min_symbols=1,
                    holdout_exclude=[], universe=["BTCUSDT", "ETHUSDT", "SOLUSDT"],
                    grid=[{"lookback_days": 7, "enter_apr": 0.01}, {"lookback_days": 7, "enter_apr": 0.02}],
                    code="research/families/fcarry.json", alpha="0.0")
        return spec

    def test_a_hand_made_version_2_is_refused_by_add_version_and_the_registered_spec_is_the_family_file(self):
        families.discover_all(self.db)
        self.revive()
        self.approve()
        self.touch()
        path = os.path.join(self.tmp, "forged.json")
        with open(path, "w") as f:
            json.dump(self.forged(families.approval_payload(self.db, "fcarry")), f)
        real, fam_blob = registry.blob_at, CLEAN["family"]["committed"]
        with mock.patch.object(registry, "blob_at",
                               lambda c, pth: fam_blob if pth.endswith("fcarry.json") else real(c, pth)), \
                mock.patch.object(registry, "git_committed", lambda p: True):
            out = cli(["add-version", F, "--spec", path], self.db_path)
            reg = fleet.strategy_pass(self.db)["registered"]
        got = pipeline._spec(self.db, F)
        print("\n[B]", out, "| registered", reg, "costs", got["costs"], "min_symbols", got["min_symbols"])
        self.assertTrue(refused(out))
        self.assertIn(F, reg)                                    # registered, but from the family file
        self.assertNotEqual(got["costs"]["taker_fee"], 0.0)
        self.assertNotEqual(got["min_symbols"], 1)
        self.assertEqual((len(got["universe"]), got["holdout_exclude"]), (30, ["BTCUSDT", "ETHUSDT", "SOLUSDT"]))

    def test_a_forged_version_2_written_straight_into_the_registry_does_not_register(self):
        families.discover_all(self.db)
        self.revive()
        self.approve()
        self.touch()
        p = families.approval_payload(self.db, "fcarry")
        v1 = registry.latest(self.db, F)
        self.db.append("experiments", exp_id=F, version=2, created_ts=0, mechanism_tag=v1["mechanism_tag"],
                       fingerprint=v1["fingerprint"], spec_json=self.forged(p), spec_path="research/families/fcarry.json",
                       spec_commit="c0ffee", code_hash=p["blobs"]["family"], note="forged")
        reg = fleet.strategy_pass(self.db)["registered"]
        print("\n[B2] registered", reg, "state", lifecycle.state(self.db, F))
        self.assertNotIn(F, reg)
        self.assertEqual(lifecycle.state(self.db, F), "DISCOVERED")


class CliBypass(A5Base):
    def test_lab_result_is_refused_and_lab_transition_never_moves_a_family_instance_screening_to_screen_passed(self):
        self.register()
        with mock.patch.dict(os.environ, {"CLAUDECODE": "1"}), \
                mock.patch.object(families, "GUARD", families.interactive_human):
            lifecycle.auto_transition(self.db, F, "SCREENING", "system:fixture", "screening starts in this test")
            out1 = cli(["result", F, "--label", "EXPLORATORY", "--verdict", "PASS forged by the CLI"], self.db_path)
            self.assertIsNone(self.db.one("SELECT MAX(id) FROM results WHERE exp_id=?", F)[0])
            with self.assertRaises(registry.RegistryError):
                registry.record_result(self.db, F, "EXPLORATORY", "PASS typed by a human", {}, {}, "human:anton")
            outs = []
            for actor in ("human:anton", "system:fixture"):     # a result already in the registry, either actor
                rid = forge(self.db, F, "EXPLORATORY", "PASS forged in the registry", {}, actor)
                outs.append(cli(["transition", F, "SCREEN_PASSED", "--reason", "forged straight to SCREEN_PASSED",
                                 "--result-id", str(rid)], self.db_path))
        print("\n[C1]", out1, outs, "-> state", lifecycle.state(self.db, F))
        self.assertTrue(refused(out1))
        self.assertTrue(all(refused(o) for o in outs))
        self.assertEqual(lifecycle.state(self.db, F), "SCREENING")

    def test_a_forged_forward_pass_neither_closes_the_family_nor_lifts_the_programme_stop(self):
        self.register()
        self.screened(F, sharpe=1.5)
        for e in (L, H):
            self.screened(e, observe=False)
        fleet.strategy_pass(self.db)
        cf = families.cohort(self.db, "fcarry")
        self.assertEqual(cf["selected"], [F])
        with mock.patch.dict(os.environ, {"CLAUDECODE": "1"}):
            out1 = cli(["result", F, "--label", "VALIDATION", "--verdict", families.FORWARD_PASS + ": forged"],
                       self.db_path)
            outs = []
            for actor, metrics in (("human:anton", {}), ("system:fixture", {}),
                                   ("system:fixture", {"cohort": cf["cohort"]})):   # no hash-recorded artifact
                rid = forge(self.db, F, "VALIDATION", families.FORWARD_PASS + ": forged", metrics, actor)
                outs.append(cli(["transition", F, "SCREEN_PASSED", "--reason", "forged forward pass, no window read",
                                 "--result-id", str(rid)], self.db_path))
        st = fleet.strategy_pass(self.db)["families"]["fcarry"]
        self.now[0] = ts(2028, 7, 2)
        print("\n[C2]", out1, outs, "state", lifecycle.state(self.db, F), "| family status:", st,
              "| forward_passes:", families.forward_passes(self.db), "| programme_stop 2028-07-02:",
              families.programme_stop(self.db))
        self.assertTrue(refused(out1))
        self.assertTrue(all(refused(o) for o in outs))
        self.assertEqual(lifecycle.state(self.db, F), "OBSERVATION")
        self.assertIsNone(families.closed(self.db, "fcarry"))
        self.assertEqual(families.forward_passes(self.db), set())
        self.assertNotEqual(families.programme_stop(self.db), [])


class PerTag(A3Base):
    def earlier(self, fid, closed=True):
        e = f"E_{fid}__x1_a8"
        self.db.append("experiments", exp_id=e, version=1, created_ts=0, mechanism_tag="delta_neutral_funding_carry",
                       fingerprint=e, spec_json={"execution": "taker", "family": fid})
        for st in ("REGISTERED", "SCREENING") + (("REJECTED",) if closed else ()):
            self.db.append("transitions", exp_id=e, ts=0, from_state=None, to_state=st, actor="fixture",
                           reason="fixture: an earlier family on the same tag")
        if closed:
            self.db.event("family.closed", "system:fixture", None, {"family": fid, "outcome": "FUTILE_IN_SAMPLE"})

    def attempt(self, fids):
        real = families.load

        def acked(path_or_fid):
            fam = real(path_or_fid)
            if fam.get("family_id") == "fcarry":
                fam["graveyard_acknowledged"] = fam["graveyard_acknowledged"] + [
                    {"exp_id": f"E_{x}__x1_a8", "match": "exact", "lessons_addressed": ["x"],
                     "materially_different_because": "materially different because a later, separately drafted family"}
                    for x in fids]
            return fam
        with mock.patch.object(families, "load", acked):
            with self.assertRaises(families.FamilyError) as cm:
                self.ready()
            reg = fleet.strategy_pass(self.db)["registered"]
        print(f"\n[D] {fids}: {cm.exception} | approval", families.approval(self.db, "fcarry"), "registered", reg)
        self.assertIsNone(families.approval(self.db, "fcarry"))
        self.assertEqual(reg, [])
        return str(cm.exception)

    def test_a_third_family_on_the_same_tag_is_refused(self):
        for fid in ("fone", "ftwo"):
            self.earlier(fid)
        self.assertIn("at most 2 families", self.attempt(["fone", "ftwo"]))

    def test_a_second_family_while_one_is_open_on_the_same_tag_is_refused(self):
        self.earlier("fone", closed=False)
        self.attempt(["fone"])


class PartialBatch(A3Base):
    def test_approval_before_the_revivals_is_refused(self):
        families.discover_all(self.db)
        with self.assertRaises(families.FamilyError):
            self.approve()
        self.revive([F])
        with self.assertRaises(families.FamilyError):
            self.approve()                                   # still before floor and hyst are revived
        self.assertEqual(fleet.strategy_pass(self.db)["registered"], [])

    def test_a_base_instance_that_is_not_discovered_at_registration_holds_the_whole_batch(self):
        self.ready()
        self.db.append("transitions", exp_id=H, ts=0, from_state="DISCOVERED", to_state="SUPPRESSED",
                       actor="fixture", reason="fixture: one base instance falls out after the approval")
        first = fleet.strategy_pass(self.db)["registered"]
        waiting = [json.loads(r[0]) for r in self.db.q("SELECT payload FROM events WHERE kind='family.waiting'")]
        self.db.append("transitions", exp_id=H, ts=0, from_state="SUPPRESSED", to_state="DISCOVERED",
                       actor="fixture", reason="fixture: back again")
        second = fleet.strategy_pass(self.db)["registered"]
        print("\n[E] first", first, "waiting", waiting[-1:], "second", second)
        self.assertEqual(first, [])
        self.assertTrue(waiting and H in json.dumps(waiting[-1]))
        self.assertEqual(sorted(second), BASE)


class HumanPaper(A3Base):
    def validated(self, e):
        for st in ("SCREENING", "OBSERVATION", "SCREEN_PASSED", "VALIDATION"):
            self.db.append("transitions", exp_id=e, ts=0, from_state=None, to_state=st, actor="fixture",
                           reason="fixture: the path to a holdout")
        rid = registry.record_result(self.db, e, "VALIDATION", "PASS (holdout): fixture", {}, {}, "system:fixture")
        self.db.append("transitions", exp_id=e, ts=0, from_state="VALIDATION", to_state="VALIDATED", actor="fixture",
                       reason="fixture: holdout passed", evidence={"result_id": rid})

    def test_paper_trading_of_a_validated_family_instance_is_refused_and_never_authorized(self):
        self.ready()
        fleet.strategy_pass(self.db)
        self.validated(L)
        with self.assertRaises(lifecycle.LifecycleError):
            code = lifecycle.request_approval(self.db, L, "PAPER_TRADING", "human:anton", "paper trade the family")
            lifecycle.confirm(self.db, code, "human:anton", guards=(registry.complete_spec_guard,
                                                                    families.terminal_guard))
        self.assertEqual(lifecycle.state(self.db, L), "VALIDATED")
        self.db.append("transitions", exp_id=L, ts=0, from_state="VALIDATED", to_state="PAPER_TRADING",
                       actor="human:anton", reason="fixture: forced straight into the registry")
        ok = promotion.trading_authorized(self.db, L)
        print("\n[F] forced PAPER_TRADING, trading_authorized", ok)
        self.assertFalse(ok[0])


class BudgetPrefix(A3Base):
    def test_a_family_prefixed_id_is_refused_and_foreign_rows_never_count_towards_w0(self):
        out = cli(["discover", "family:zzz", "--hypothesis", "h", "--mechanism", "m", "--instrument", "i", "--horizon",
                   "days", "--execution", "taker", "--source", "s"], self.db_path)
        self.assertTrue(refused(out))
        for eid, note in (("family:zzz", "version 2"), ("family:fcarry", "version 2"), ("family:fcarry", "manual")):
            self.db.append("alpha_ledger", exp_id=eid, ts=0, alpha=-0.05, note=note)   # straight into the ledger
        self.assertAlmostEqual(families.alpha_reserved(self.db), 0.0)
        self.assertAlmostEqual(families.reserved(self.db, "fcarry"), 0.0)
        for fid in ("fa", "fb", "fc", "fd"):                     # four real families already hold W0 = 0.05
            self.db.append("alpha_ledger", exp_id=f"family:{fid}", ts=0, alpha=0.0125, note="A8 reserve")
        with self.assertRaises(families.FamilyError):
            self.ready()                                         # a fifth family
        total = self.db.one("SELECT SUM(alpha) FROM alpha_ledger WHERE note='A8 reserve'")[0]
        print("\n[G]", out, "alpha_reserved:", families.alpha_reserved(self.db), "A8 reserve rows:", total)
        self.assertIsNone(families.approval(self.db, "fcarry"))
        self.assertLessEqual(total, families.W0 + 1e-12)


class DiscoverBypass(A3Base):
    def test_lab_discover_of_a_family_instance_id_is_refused_and_suppression_still_applies(self):
        outs = [cli(["discover", e, "--hypothesis", "h", "--mechanism", "harmless_tag", "--instrument", "i",
                     "--horizon", "days", "--execution", "taker", "--source", "s"], self.db_path) for e in BASE]
        families.discover_all(self.db)
        states = {e: lifecycle.state(self.db, e) for e in BASE}
        with self.assertRaises(families.FamilyError):
            self.approve()                                       # no revival: the base instances are SUPPRESSED
        print("\n[H]", outs, "states", states)
        self.assertTrue(all(refused(o) for o in outs))
        self.assertEqual(set(states.values()), {"SUPPRESSED"})
        self.assertEqual({r[0] for r in self.db.q("SELECT DISTINCT mechanism_tag FROM experiments WHERE exp_id IN "
                                                  "(?,?,?)", *BASE)}, {"delta_neutral_funding_carry"})

    def test_a_version_2_under_another_tag_written_straight_into_the_registry_does_not_register(self):
        self.ready()
        p = families.approval_payload(self.db, "fcarry")
        v1 = registry.latest(self.db, F)
        engine = {f: "blob-test" for f in pipeline.ENGINE_CODE}
        self.db.append("experiments", exp_id=F, version=2, created_ts=0, mechanism_tag="harmless_tag",
                       fingerprint=v1["fingerprint"], spec_json=families.instance_spec(FCARRY, "filt", p["blobs"], engine),
                       spec_path="research/families/fcarry.json", spec_commit="c0ffee", code_hash=p["blobs"]["family"],
                       note="forged tag")
        reg = fleet.strategy_pass(self.db)["registered"]
        print("\n[H2] registered", reg, "state", lifecycle.state(self.db, F))
        self.assertNotIn(F, reg)
        self.assertEqual(lifecycle.state(self.db, F), "DISCOVERED")


if __name__ == "__main__":
    unittest.main()
