"""Hypothesis families (research/PROTOCOL_V3.md amendment 8), phase A1: the family file, the vocabulary rules, the
power rule and the read-only family-check."""
import copy
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lab import families  # noqa: E402
from lab.__main__ import main  # noqa: E402
from lab.db import DB  # noqa: E402
from lab.engine import catalogue  # noqa: E402

FCARRY = families.load("fcarry")


def problems_of(**change):
    fam = copy.deepcopy(FCARRY)
    for path, value in change.items():
        node, keys = fam, path.split("__")
        for k in keys[:-1]:
            node = node[int(k)] if isinstance(node, list) else node[k]
        last = keys[-1]
        if isinstance(node, list):
            node[int(last)] = value
        else:
            node[last] = value
    return families.validate(fam)


class FamilyFile(unittest.TestCase):
    def test_the_first_family_meets_every_rule(self):
        self.assertEqual(families.validate(FCARRY), [])

    def test_refusals(self):
        four = copy.deepcopy(FCARRY["instances"]) + [dict(FCARRY["instances"][0], id="extra", successor=None)]
        cases = {
            "K = 4": {"instances": four},
            "3 variants": {"instances__0__grid": FCARRY["instances"][0]["grid"] + [{"lookback_days": 7, "enter_apr": 0.3}]},
            "lookback 30": {"instances__1__max_lookback_days": 30},
            "9 months": {"forward__months": 9},
            "unknown tag": {"mechanism__tag": "made_up_tag"},
            "price prediction": {"mechanism__tag": "time_series_momentum"},
            "not hedged": {"mechanism__price_exposure": "directional"},
            "short acknowledgement": {"graveyard_acknowledged__0__materially_different_because": "materially different because"},
            "successor on validation": {"instances__0__successor__trigger__artifact": "validate"},
            "alpha too large": {"alpha__family": 0.05},
            "costs below catalogue": {"costs__taker_fee": 0.0001},
            "decided at midnight": {"decision_time_utc": "00:00"},
            "window before December": {"forward__earliest_start": "2026-11-01"},
        }
        for name, change in cases.items():
            with self.subTest(name):
                self.assertTrue(problems_of(**change), name)

    def test_a_related_tag_must_be_reviewed(self):
        self.assertTrue(any("related tags not reviewed" in p for p in problems_of(related_tags_reviewed=[])))


class Power(unittest.TestCase):
    def test_required_sharpe_matches_amendments_7_and_8(self):
        self.assertAlmostEqual(families.required_sharpe(0.0125, 12), 2.25, places=2)
        self.assertAlmostEqual(families.required_sharpe(0.0125 / 3, 12), 2.65, places=1)
        self.assertAlmostEqual(families.required_sharpe(0.005, 6), 3.69, places=1)    # amendment 7's 'cirka 3,7'
        self.assertAlmostEqual(families.required_sharpe(0.0125, 6), 3.21, places=1)

    def test_power_rule_needs_twelve_months(self):
        self.assertGreaterEqual(families.power(3.0, 0.0125 / 3, 12), 0.5)
        self.assertLess(families.power(3.0, 0.0125 / 3, 6), 0.5)


class CatalogueUntouched(unittest.TestCase):
    def test_no_family_code_touches_the_catalogue(self):
        before = json.dumps(sorted(catalogue.TEMPLATES), sort_keys=True)
        families.validate(FCARRY)
        families.expected_files(FCARRY)
        self.assertEqual(json.dumps(sorted(catalogue.TEMPLATES), sort_keys=True), before)
        self.assertNotIn("fcarry", " ".join(catalogue.TEMPLATES))

    def test_every_catalogue_tag_is_price_prediction_in_the_vocabulary(self):
        v = families.vocabulary()["tags"]
        for t in catalogue.TEMPLATES.values():
            self.assertEqual(v[t["mechanism_tag"]]["class"], "price_prediction", t["mechanism_tag"])


class Check(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="labfam")
        self.path = os.path.join(self.tmp, "lab.db")
        db = DB(self.path)
        for eid, tag in (("L13_carry_v1", "delta_neutral_funding_carry"), ("L08_funding_carry_leverage", "funding_carry_leverage"),
                         ("E_funding_contrarian_p1", "funding_crowding_contrarian"), ("L22_m3_premium_convergence", "perp_premium_convergence"),
                         ("L99_new_related", "funding_carry")):
            db.append("experiments", exp_id=eid, version=1, created_ts=0, mechanism_tag=tag, fingerprint=eid,
                      spec_json={"execution": "taker"})
            db.append("transitions", exp_id=eid, ts=0, from_state=None, to_state="REJECTED", actor="fixture",
                      reason="fixture: rejected")
        db.close()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_an_unacknowledged_graveyard_relative_is_a_problem(self):
        db = DB(self.path)
        try:
            hits, unacked = families.graveyard_hits(db, FCARRY)
        finally:
            db.close()
        self.assertIn("L13_carry_v1", hits)
        self.assertEqual(unacked, ["L99_new_related"])

    def test_family_check_is_read_only_and_never_uses_the_network(self):
        before = os.path.getmtime(self.path), os.path.getsize(self.path)
        lines = []

        def no_network(*a, **k):
            raise AssertionError("family-check must not use the network")
        with mock.patch("urllib.request.urlopen", no_network), mock.patch("socket.create_connection", no_network):
            rc = main(["family-check", families.path_of("fcarry")], self.path, lines.append)
        text = "\n".join(lines)
        self.assertEqual(rc, 1, text)                                  # L99 is not acknowledged
        self.assertIn("L99_new_related", text)
        self.assertIn("required annualised Sharpe over 12 months", text)
        self.assertIn("cache data/lab/market/spot_klines", text)
        self.assertEqual((os.path.getmtime(self.path), os.path.getsize(self.path)), before)
        con = sqlite3.connect(self.path)
        self.assertEqual(con.execute("SELECT COUNT(*) FROM events").fetchone()[0], 0)
        con.close()


CLEAN = {k: {"path": k, "committed": c, "working": c, "clean": True}
         for k, c in (("family", "abcdef0123456789"), ("module", "1111"), ("adapter", "2222"), ("vocabulary", "3333"))}


class Approval(unittest.TestCase):
    """Phase A2: approval typed by the user, alpha budget and binding (amendment 8 points 5 and 13)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="labfamA2")
        self.db = DB(os.path.join(self.tmp, "lab.db"))
        for eid in ("L13_carry_v1", "L08_funding_carry_leverage", "E_funding_contrarian_p1", "L22_m3_premium_convergence"):
            self.db.append("experiments", exp_id=eid, version=1, created_ts=0, mechanism_tag="x", fingerprint=eid,
                           spec_json={})
        self.blobs = copy.deepcopy(CLEAN)
        self.p = [mock.patch.object(families, "GUARD", lambda: None),
                  mock.patch.object(families, "blobs", lambda fid: copy.deepcopy(self.blobs)),
                  mock.patch.object(families.os.path, "exists",
                                    lambda p, _real=os.path.exists: True if p.endswith("fcarry.py") else _real(p))]
        for p in self.p:
            p.start()

    def tearDown(self):
        for p in self.p:
            p.stop()
        self.db.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def approve(self, prefix="abcdef01"):
        code = families.request(self.db, "fcarry", "human:anton", "Anton approves F1 after reading it")
        return families.confirm(self.db, code, prefix, "human:anton")

    def test_only_an_interactive_human_outside_an_assistant_session(self):
        self.p[0].stop()
        try:
            with mock.patch.dict(os.environ, {"CLAUDECODE": "1"}):
                with self.assertRaises(families.FamilyError):
                    families.request(self.db, "fcarry", "human:anton", "Anton approves F1 after reading it")
            env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE" and not k.startswith("CLAUDE_CODE_")}
            with mock.patch.dict(os.environ, env, clear=True), mock.patch("sys.stdin.isatty", lambda: False):
                with self.assertRaises(families.FamilyError):
                    families.request(self.db, "fcarry", "human:anton", "Anton approves F1 after reading it")
        finally:
            self.p[0].start()
        with self.assertRaises(families.FamilyError):
            families.request(self.db, "fcarry", "agent:strategy-1", "an agent cannot approve a family")

    def test_two_steps_reserve_alpha_and_bind_the_files(self):
        with self.assertRaises(families.FamilyError):
            self.approve(prefix="00000000")                                    # wrong blob prefix
        fid, eid = self.approve()
        self.assertEqual(fid, "fcarry")
        self.assertEqual(families.approval(self.db, "fcarry"), eid)
        self.assertAlmostEqual(families.alpha_reserved(self.db), 0.0125)
        self.blobs["module"]["committed"] = self.blobs["module"]["working"] = "9999"
        self.assertIsNone(families.approval(self.db, "fcarry"))               # a bound file changed
        self.blobs["module"]["committed"] = self.blobs["module"]["working"] = "1111"
        self.assertEqual(families.approval(self.db, "fcarry"), eid)
        with mock.patch.object(families, "thresholds", lambda: {"changed": True}):
            self.assertIsNone(families.approval(self.db, "fcarry"))           # a bound gate value changed

    def test_codes_expire_and_are_used_once(self):
        code = families.request(self.db, "fcarry", "human:anton", "Anton approves F1 after reading it", now=1000)
        with self.assertRaises(families.FamilyError):
            families.confirm(self.db, code, "abcdef01", "human:anton", now=1000 + families.APPROVAL_SECONDS + 1)
        families.confirm(self.db, code, "abcdef01", "human:anton", now=1001)
        with self.assertRaises(families.FamilyError):
            families.confirm(self.db, code, "abcdef01", "human:anton", now=1002)

    def test_the_budget_refuses_a_family_that_does_not_fit(self):
        self.db.append("alpha_ledger", exp_id="family:other", ts=0, alpha=0.045, note="A8 reserve")
        with self.assertRaises(families.FamilyError):
            self.approve()
        self.db.append("alpha_ledger", exp_id="E_screening_only", ts=0, alpha=0.005, note="screening")
        self.assertAlmostEqual(families.alpha_reserved(self.db), 0.045)       # screening rows are not A8 wealth

    def test_revoke_releases_alpha_only_before_registration(self):
        self.approve()
        self.assertAlmostEqual(families.revoke(self.db, "fcarry", "human:anton", "Anton withdraws F1 for now"), 0.0125)
        self.assertAlmostEqual(families.alpha_reserved(self.db), 0.0)
        self.assertIsNone(families.approval(self.db, "fcarry"))
        self.approve()
        self.db.append("experiments", exp_id="E_fcarry__filt_a8", version=1, created_ts=0, mechanism_tag="x",
                       fingerprint="f", spec_json={})
        with self.assertRaises(families.FamilyError):
            families.revoke(self.db, "fcarry", "human:anton", "too late: already registered")

    def test_a_family_code_cannot_execute_a_lifecycle_transition(self):
        from lab import lifecycle
        code = families.request(self.db, "fcarry", "human:anton", "Anton approves F1 after reading it")
        with self.assertRaises(Exception):
            lifecycle.confirm(self.db, code, "human:anton")
        self.assertEqual(self.db.one("SELECT COUNT(*) FROM transitions")[0], 0)

    def test_the_cli_asks_for_the_code_and_the_blob_prefix_at_the_prompt(self):
        import argparse
        from lab.__main__ import family_cmd
        code = families.request(self.db, "fcarry", "human:anton", "Anton approves F1 after reading it")
        answers, lines = iter([code, "abcdef01"]), []
        rc = family_cmd(argparse.Namespace(cmd="confirm-family"), self.db, lines.append, ask=lambda q: next(answers))
        self.assertEqual(rc, 0, lines)
        self.assertIn("family.approved", lines[-1])
        lines.clear()
        self.assertEqual(family_cmd(argparse.Namespace(cmd="families"), self.db, lines.append), 0)
        self.assertTrue(any(line.strip().startswith("fcarry: approved") for line in lines), lines)

    def test_a_catalogue_change_does_not_void_a_family_approval(self):
        _, eid = self.approve()
        with mock.patch("lab.templates.catalogue_blob", lambda: "a-different-catalogue-blob"):
            self.assertEqual(families.approval(self.db, "fcarry"), eid)


if __name__ == "__main__":
    unittest.main()
