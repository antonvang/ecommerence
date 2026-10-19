"""Hypothesis families (research/PROTOCOL_V3.md amendment 8 with amendment 9 point 1): the design (C) test list 1-28 of
research/AENDRING8_DESIGN.md over phases A1-A6, on synthetic data only (data._fetch raises in every family test)."""
import copy
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import types
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
        self.assertTrue(problems_of(forward__months=6))                     # a 6-month family is refused (test 5)


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


def discovered(db, fid="fcarry", fam=None):
    """The family's base instances DISCOVERED exactly as discover_all writes them (approve-family needs every base
    instance revived first, amendment 8 point 6), for tests that approve without the discovery agent."""
    from lab import registry as reg
    fam = fam or FCARRY
    for i in fam["instances"]:
        e, tag = families.exp_id(fid, i["id"]), fam["mechanism"]["tag"]
        db.append("experiments", exp_id=e, version=1, created_ts=0, mechanism_tag=tag,
                  fingerprint=reg.fingerprint(tag, families.instrument(fam), i["horizon"], i["execution"]),
                  spec_json={"family": fid, "instance": i["id"], "discovered_by": "discovery-catalogue"},
                  note="discovered")
        db.append("transitions", exp_id=e, ts=0, from_state=None, to_state="DISCOVERED", actor="discovery-catalogue",
                  reason="fixture: discovered from the family file")


class Approval(unittest.TestCase):
    """Phase A2: approval typed by the user, alpha budget and binding (amendment 8 points 5 and 13)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="labfamA2")
        self.db = DB(os.path.join(self.tmp, "lab.db"))
        for eid in ("L13_carry_v1", "L08_funding_carry_leverage", "E_funding_contrarian_p1", "L22_m3_premium_convergence"):
            self.db.append("experiments", exp_id=eid, version=1, created_ts=0, mechanism_tag="x", fingerprint=eid,
                           spec_json={})
        discovered(self.db)                                    # revival comes before approve-family (point 6)
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
        self.assertFalse(families.registered(self.db, "fcarry"))          # a discovered candidate is not registered
        self.db.append("transitions", exp_id="E_fcarry__filt_a8", ts=0, from_state="DISCOVERED", to_state="REGISTERED",
                       actor="fixture", reason="fixture: registered")
        with self.assertRaises(families.FamilyError):
            families.revoke(self.db, "fcarry", "human:anton", "too late: already registered")

    def test_a_family_code_cannot_execute_a_lifecycle_transition(self):
        from lab import lifecycle
        code = families.request(self.db, "fcarry", "human:anton", "Anton approves F1 after reading it")
        before = self.db.one("SELECT COUNT(*) FROM transitions")[0]
        with self.assertRaises(Exception):
            lifecycle.confirm(self.db, code, "human:anton")
        self.assertEqual(self.db.one("SELECT COUNT(*) FROM transitions")[0], before)

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


# ---------- phase A3: discovery, registration, spot cache, embargo (design (C) tests 2, 3, 7-11) ----------
import urllib.error  # noqa: E402
from datetime import datetime, timezone  # noqa: E402
from lab import explore, fleet, jobs, lifecycle, pipeline, registry, templates  # noqa: E402
from lab.engine import data  # noqa: E402

GRAVE = (("L13_carry_v1", "delta_neutral_funding_carry"), ("L08_funding_carry_leverage", "funding_carry_leverage"),
         ("E_funding_contrarian_p1", "funding_crowding_contrarian"),
         ("L22_m3_premium_convergence", "perp_premium_convergence"))
BASE = ["E_fcarry__filt_a8", "E_fcarry__floor_a8", "E_fcarry__hyst_a8"]
ALL4 = BASE + ["E_fcarry__filt_w_a8"]
WHY = "materially different because Binance spot/perp pairs of 30 coins, low turnover, attribution gate, forward test"


def ts(*ymd_hms):
    return int(datetime(*ymd_hms, tzinfo=timezone.utc).timestamp())


class A3Base(unittest.TestCase):
    """A temporary registry with the graveyard of design (D), a temporary market cache, a fixed clock, and no network:
    data._fetch raises in every test unless a test replaces it with a recorder."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="labfamA3")
        self.cache = os.path.join(self.tmp, "market")
        self.db_path = os.path.join(self.tmp, "lab.db")
        self.db = DB(self.db_path)
        for eid, tag in GRAVE:
            self.grave(eid, tag)
        self.blobs = copy.deepcopy(CLEAN)
        self.now = [ts(2026, 11, 20)]

        def no_fetch(url, path, get=None):
            raise AssertionError(f"a family test tried to fetch {url}")

        def no_network(*a, **k):
            raise AssertionError("a family test used the network")
        self.p = [mock.patch.object(families, "GUARD", lambda: None),
                  mock.patch.object(families, "blobs", lambda fid: copy.deepcopy(self.blobs)),
                  mock.patch.object(families.os.path, "exists",
                                    lambda p, _real=os.path.exists: True if p.endswith("fcarry.py") else _real(p)),
                  mock.patch.object(data, "CACHE", self.cache),
                  mock.patch.object(data, "CLOCK", lambda: self.now[0]),
                  mock.patch.object(data, "_fetch", no_fetch),
                  mock.patch.object(families, "_urlopen", no_network),
                  mock.patch("urllib.request.urlopen", no_network),
                  mock.patch.object(lifecycle, "git_committed", lambda p: True),
                  mock.patch.object(registry, "last_commit", lambda p: "c0ffee"),
                  mock.patch.object(registry, "blob_at", lambda c, p: "blob-test"),
                  mock.patch.object(templates, "catalogue_blob", lambda: "blob-test"),
                  mock.patch.object(pipeline, "ARTIFACTS", os.path.join(self.tmp, "artifacts")),
                  mock.patch.object(pipeline, "REPORTS", os.path.join(self.tmp, "reports")),
                  mock.patch.object(fleet, "PROCESSES", False),
                  # amendment 8 tests run without the amendment 10 lane, which would fetch explore0 for an approved
                  # family through the fleet; tests/test_lab_explore.py covers the lane
                  mock.patch.object(explore, "eligible", lambda db: []),
                  mock.patch.object(fleet.control, "ram", lambda: {"total": 16e9, "free": 8e9, "load_pct": 50})]
        for p in self.p:
            p.start()

    def tearDown(self):
        for p in self.p:
            p.stop()
        self.db.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def grave(self, eid, tag, state="REJECTED"):
        self.db.append("experiments", exp_id=eid, version=1, created_ts=0, mechanism_tag=tag, fingerprint=eid,
                       spec_json={"execution": "taker"})
        self.db.append("transitions", exp_id=eid, ts=0, from_state=None, to_state=state, actor="fixture",
                       reason="fixture: graveyard row")

    def touch(self, kinds=("klines", "funding", "spot"), splits=families.SCREEN_SPLITS, skip=()):
        n = 0
        for sp in splits:
            for s in data.UNIVERSE_30_V3:
                for kind, pairs in data.expected_paths(s, sp, spot=True).items():
                    for _, p in pairs:
                        if kind in kinds and p not in skip:
                            os.makedirs(os.path.dirname(p), exist_ok=True)
                            open(p, "wb").close()
                            n += 1
        return n

    def approve(self):
        code = families.request(self.db, "fcarry", "human:anton", "Anton approves F1 after reading it")
        return families.confirm(self.db, code, "abcdef01", "human:anton")

    def revive(self, eids=ALL4):
        for e in eids:
            code = lifecycle.request_approval(self.db, e, "DISCOVERED", "human:anton", WHY)
            lifecycle.confirm(self.db, code, "human:anton", guards=(registry.complete_spec_guard,
                                                                     families.terminal_guard))

    def ready(self, files=True):
        families.discover_all(self.db)
        self.revive()
        self.approve()
        if files:
            self.touch()

    def events(self, kind):
        return [json.loads(r[0]) for r in self.db.q("SELECT payload FROM events WHERE kind=? ORDER BY id", kind)]

    def queue_on_the_fixture_clock(self):
        """The job queue (enqueue, claim, defer, runnable_any) reads the fixture clock, so a test about dates is not red
        once the wall clock passes them."""
        p = mock.patch.object(jobs, "time", types.SimpleNamespace(time=lambda: self.now[0]))
        p.start()
        self.addCleanup(p.stop)

    def family_batches(self):
        return [b for b in self.events("batch.registered") if b.get("family")]


class Discovery(A3Base):
    def test_instances_are_discovered_and_suppressed_by_the_exact_graveyard_hit(self):
        out = families.discover_all(self.db)
        self.assertEqual(sorted(e for e, _, _ in out), sorted(ALL4))           # base instances and the successor
        for e, st, dup in out:
            self.assertEqual((st, dup), ("SUPPRESSED", ["L13_carry_v1"]), e)
        spec = json.loads(registry.latest(self.db, "E_fcarry__filt_w_a8")["spec_json"])
        self.assertEqual((spec["family"], spec["instance"], spec["parent"], spec["template"]),
                         ("fcarry", "filt_w", "filt", "fcarry__filt_w"))
        self.assertEqual(families.discover_all(self.db), [])                   # idempotent
        self.assertFalse(families.registered(self.db, "fcarry"))               # candidates are not registrations
        with self.assertRaises(families.FamilyError) as c:                     # point 6: revival before approve-family
            self.approve()
        self.assertIn(families.REVIVE_FIRST, str(c.exception))
        self.revive()
        self.approve()                                                        # approval after discovery and revival

    def test_the_catalogue_pass_discovers_both(self):
        res = fleet.catalogue_pass(self.db)
        ids = {r["exp_id"] for r in res}
        self.assertTrue(set(ALL4) <= ids)
        self.assertEqual(len([i for i in ids if i.endswith("_a8")]), 4)
        self.assertEqual(len(ids - set(ALL4)), len(catalogue.TEMPLATES))

    def test_only_committed_valid_family_files_and_errors_stay_per_family(self):
        with mock.patch.object(lifecycle, "git_committed", lambda p: False):
            self.assertEqual(families.discover_all(self.db), [])
        with mock.patch.object(families, "validate", lambda fam, vocab=None: ["broken"]):
            self.assertEqual(families.discover_all(self.db), [])
        with mock.patch.object(families, "load", mock.Mock(side_effect=ValueError("bad json"))):
            out = families.discover_all(self.db)
        self.assertEqual(out[0][0], "family:fcarry")
        self.assertTrue(out[0][1].startswith("error"))
        self.assertIsNone(registry.latest(self.db, "E_fcarry__filt_a8"))

    def test_a_successor_is_never_suppressed_by_its_own_sibling(self):
        self.grave("E_fcarry__filt_a8", "delta_neutral_funding_carry")         # a rejected sibling
        out = {e: dup for e, _, dup in families.discover_all(self.db)}
        self.assertEqual(out["E_fcarry__filt_w_a8"], ["L13_carry_v1"])

    def test_revival_is_human_with_materially_different_and_a_terminal(self):
        families.discover_all(self.db)
        e = "E_fcarry__filt_a8"
        with self.assertRaises(lifecycle.LifecycleError):
            lifecycle.request_approval(self.db, e, "DISCOVERED", "human:anton", "please revive this one now")
        with self.assertRaises(lifecycle.LifecycleError):
            lifecycle.auto_transition(self.db, e, "DISCOVERED", "system:strategy-1", WHY)
        self.revive([e])
        self.assertEqual(lifecycle.state(self.db, e), "DISCOVERED")


class TerminalOnly(A3Base):
    """Test 3, TTY parts: reviving a family instance through `lab confirm` needs an interactive terminal outside an
    assistant session; the dashboard has no route for it; other experiments are unchanged."""

    def cli(self, *argv):
        from lab.__main__ import main
        lines = []
        rc = main(list(argv), self.db_path, lines.append)
        return rc, "\n".join(lines)

    def code(self, eid):
        rc, text = self.cli("approve", eid, "DISCOVERED", "--reason", WHY)
        self.assertEqual(rc, 0, text)
        return text.split(": ")[1].split()[0]

    def test_lab_confirm_of_a_family_instance_needs_a_terminal(self):
        families.discover_all(self.db)
        e = "E_fcarry__filt_a8"
        code = self.code(e)
        self.p[0].stop()                                                      # the real guard
        clean = {k: v for k, v in os.environ.items() if k != "CLAUDECODE" and not k.startswith("CLAUDE_CODE_")}
        try:
            for env, stdin, stdout in (({**clean, "CLAUDECODE": "1"}, True, True),
                                       ({**clean, "CLAUDE_CODE_ENTRYPOINT": "cli"}, True, True),
                                       (clean, False, True), (clean, True, False)):
                with mock.patch.dict(os.environ, env, clear=True), mock.patch("sys.stdin.isatty", lambda v=stdin: v), \
                        mock.patch("sys.stdout.isatty", lambda v=stdout: v):
                    rc, text = self.cli("confirm", code)
                self.assertEqual(rc, 1, text)
                self.assertIn("refused", text)
                self.assertEqual(lifecycle.state(self.db, e), "SUPPRESSED")
            with mock.patch.dict(os.environ, clean, clear=True), mock.patch("sys.stdin.isatty", lambda: True), \
                    mock.patch("sys.stdout.isatty", lambda: True):
                rc, text = self.cli("confirm", code)
        finally:
            self.p[0].start()
        self.assertEqual(rc, 0, text)
        self.assertEqual(lifecycle.state(self.db, e), "DISCOVERED")

    def test_other_experiments_keep_their_confirm(self):
        self.grave("E_taker_pressure_p3", "orderflow_imbalance", state="SUPPRESSED")
        code = self.code("E_taker_pressure_p3")
        self.p[0].stop()
        try:
            with mock.patch.dict(os.environ, {"CLAUDECODE": "1"}), mock.patch("sys.stdin.isatty", lambda: False):
                rc, text = self.cli("confirm", code)
        finally:
            self.p[0].start()
        self.assertEqual(rc, 0, text)
        self.assertEqual(lifecycle.state(self.db, "E_taker_pressure_p3"), "DISCOVERED")

    def test_a_family_code_is_refused_by_lab_confirm_with_the_right_command(self):
        families.discover_all(self.db)
        self.revive()                                                         # revival before approve-family
        code = families.request(self.db, "fcarry", "human:anton", "Anton approves F1 after reading it")
        rc, text = self.cli("confirm", code)
        self.assertEqual(rc, 1)
        self.assertIn("python3 -m lab confirm-family", text)
        self.assertIsNone(families.approval(self.db, "fcarry"))

    def test_the_dashboard_has_no_route_for_family_instances(self):
        import threading
        import urllib.request as ur
        from lab import web
        families.discover_all(self.db)
        code = lifecycle.request_approval(self.db, "E_fcarry__hyst_a8", "DISCOVERED", "human:anton", WHY)
        srv = web.LabServer(("127.0.0.1", 0), self.db_path)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        real = self.p[7]
        real.stop()                                                          # local loopback only, for the dashboard
        try:
            def post(path, body):
                req = ur.Request(f"http://127.0.0.1:{srv.server_address[1]}{path}", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", "X-Lab-Token": srv.token})
                try:
                    with ur.urlopen(req, timeout=10) as r:
                        return r.status, json.loads(r.read())
                except urllib.error.HTTPError as e:
                    return e.code, json.loads(e.read())
            st, body = post("/api/control/approve", {"exp_id": "E_fcarry__filt_a8", "to": "DISCOVERED", "reason": WHY})
            self.assertEqual(st, 400, body)
            self.assertIn("family instance", body["error"])
            st, body = post("/api/control/confirm", {"code": code})
            self.assertEqual(st, 400, body)
            for path in ("/api/control/approve-family", "/api/control/confirm-family"):
                self.assertEqual(post(path, {"fid": "fcarry"})[0], 404)
        finally:
            real.start()
            srv.shutdown()
            srv.server_close()
        self.assertEqual(lifecycle.state(self.db, "E_fcarry__hyst_a8"), "SUPPRESSED")


class Registration(A3Base):
    def test_mixed_catalogue_and_family_ids_register_in_separate_batches(self):
        """Test 9: no StepError; the catalogue batch is exactly as before; one family batch with the trial cutoff,
        validate waiting for every member's cost step and the family priority."""
        pipeline.discover_catalogue(self.db)
        code = templates.request(self.db, "day_of_week", "human:test", "fixture approval for tests")
        templates.confirm(self.db, code, "human:test")
        self.ready()
        self.db.append("trials", exp_id="X", ts=1, variant=0, split="train", sharpe_daily=0.1, n_days=10,
                       net_total=0.0, params={})
        found = [x["exp_id"] for x in registry.status(self.db) if x["state"] == "DISCOVERED"]
        got = pipeline.register_batch(self.db, found, "strategy-1")
        self.assertEqual(sorted(got), sorted(["E_day_of_week_p2"] + BASE))
        cat = [b for b in self.events("batch.registered") if not b.get("family")]
        self.assertEqual(cat, [{"batch": "B-" + __import__("hashlib").sha256(b"E_day_of_week_p2").hexdigest()[:12],
                                "exp_ids": ["E_day_of_week_p2"], "trial_cutoff_id": 1, "protocol_version": 2}])
        fam = self.family_batches()
        self.assertEqual(len(fam), 1)
        self.assertEqual((fam[0]["family"], fam[0]["exp_ids"], fam[0]["trial_cutoff_id"], fam[0]["protocol_version"]),
                         ("fcarry", BASE, 1, 3))
        for e in BASE:
            self.assertEqual(lifecycle.state(self.db, e), "REGISTERED")
            v = jobs.get(self.db, f"validate|{e}")
            self.assertEqual(sorted(v["depends_on"]), sorted([f"adversarial|{e}"] + [f"cost|{m}" for m in BASE
                                                                                     if m != e]))
            self.assertEqual(v["priority"], families.PRIORITY)
        self.assertEqual(jobs.get(self.db, "data|E_day_of_week_p2")["priority"],
                         20 + list(catalogue.TEMPLATES).index("day_of_week"))
        self.assertEqual((jobs.get(self.db, "data|E_day_of_week_p2")["timeout_s"],
                          jobs.get(self.db, "data|E_fcarry__filt_a8")["timeout_s"]), (300, 1800))
        self.assertEqual(lifecycle.state(self.db, "E_fcarry__filt_w_a8"), "DISCOVERED")   # successor: not in batch
        again = [e for e in found if e.endswith("_a8")]
        self.assertEqual(pipeline.register_batch(self.db, again, "strategy-1"), [])        # registered once
        self.assertEqual(self.events("family.waiting"), [])

    def test_the_spec_is_complete_and_bound_to_the_approved_family_file(self):
        """Test 10."""
        self.ready()
        fleet.strategy_pass(self.db)
        e = "E_fcarry__filt_a8"
        v = registry.latest(self.db, e)
        spec = json.loads(v["spec_json"])
        self.assertEqual(v["version"], 2)
        self.assertEqual([k for k in registry.REQUIRED_SPEC if not spec.get(k)], [])
        self.assertIsInstance(spec["alpha"], dict)
        with self.assertRaises(TypeError):
            float(spec["alpha"])                                              # never through registry.add_version
        self.assertEqual((v["spec_path"], v["code_hash"]), ("research/families/fcarry.json", CLEAN["family"]["committed"]))
        self.assertEqual((spec["template"], spec["family"], spec["instance"], spec["protocol_version"], spec["amendment"]),
                         ("fcarry__filt", "fcarry", "filt", 3, 8))
        self.assertEqual(spec["code_blobs"]["module"], CLEAN["module"]["committed"])
        self.assertEqual(set(pipeline.ENGINE_CODE) | {"family", "module", "adapter", "vocabulary"},
                         set(spec["code_blobs"]))
        self.assertEqual(spec["benchmark_costs"], catalogue.COSTS)
        self.assertEqual((spec["universe"], spec["min_symbols"]), (list(data.UNIVERSE_30_V3), 24))
        self.assertFalse(spec["observation_test"])                           # never the amendment 2 route
        rows = self.db.q("SELECT alpha, note FROM alpha_ledger WHERE exp_id=?", e)
        self.assertEqual([tuple(r) for r in rows], [(0.0, "A8 in-sample filter")])
        tr = self.db.one("SELECT actor, evidence FROM transitions WHERE exp_id=? AND to_state='REGISTERED'", e)
        self.assertEqual(json.loads(tr["evidence"])["family_approval_event"], families.approval(self.db, "fcarry"))
        self.assertEqual(pipeline._code_hash(spec), CLEAN["family"]["committed"])
        with mock.patch.object(registry, "blob_at", lambda c, p: "another-catalogue-blob"):
            self.assertEqual(pipeline._code_hash(spec), CLEAN["family"]["committed"])   # a catalogue change: no lock

    def test_the_template_view_calls_the_mechanism_module_with_the_cross_sectional_convention(self):
        import types
        self.ready()
        fleet.strategy_pass(self.db)
        spec = pipeline._spec(self.db, "E_fcarry__filt_a8")
        calls = []
        fake = types.ModuleType("lab.families.fcarry")
        fake.carry_filter = lambda b, f, p, fit=None, volume_by=None, extra=None: (
            calls.append((p, fit, volume_by, extra)) or {s: [0.0] * len(x) for s, x in b.items()})
        bars = {"BTCUSDT": [(i * 3600, 1.0, 1.0) for i in range(30)]}
        with mock.patch.dict(sys.modules, {"lab.families.fcarry": fake}):
            tpl = pipeline._tpl(spec)
            self.assertTrue(tpl["cross_sectional"] and not tpl.get("needs") and tpl["universe"] == "30v3")
            pos = pipeline._positions(tpl, bars, {"BTCUSDT": {}}, spec["grid"][0], None)
            res = pipeline.adversarial.truncation_test_xs(pipeline._family(tpl), bars, {"BTCUSDT": {}},
                                                          spec["grid"][0], 3)
        self.assertEqual(pos, {"BTCUSDT": [0.0] * 30})
        self.assertTrue(res["ok"])
        self.assertEqual(calls[0], (spec["grid"][0], None, None, None))
        self.assertEqual(pipeline._min_symbols(spec), 24)
        self.assertEqual(pipeline._universe(spec), data.UNIVERSE_30_V3)

    def test_a_void_approval_or_missing_alpha_registers_nothing(self):
        """Test 2: changing any of the 4 bound files or a bound gate value voids the approval; without its reserved
        alpha nothing registers either. Changed with finding protocol-statistics #3: this test released the alpha with a
        row of another note, which no longer counts; an A8 release row does."""
        self.ready()
        for k in ("family", "module", "adapter", "vocabulary"):
            with self.subTest(k):
                old = self.blobs[k]["committed"]
                self.blobs[k]["committed"] = self.blobs[k]["working"] = "changed"
                self.assertIsNone(families.approval(self.db, "fcarry"))
                self.assertEqual(fleet.strategy_pass(self.db)["registered"], [])
                self.blobs[k]["committed"] = self.blobs[k]["working"] = old
        with mock.patch.object(families, "thresholds", lambda: {"DSR_MIN": 0.9}):
            self.assertEqual(fleet.strategy_pass(self.db)["registered"], [])
        self.db.append("alpha_ledger", exp_id="family:fcarry", ts=0, alpha=-0.0125, note="fixture: released")
        self.assertAlmostEqual(families.reserved(self.db, "fcarry"), 0.0125)  # not an A8 row: it frees nothing
        self.db.append("alpha_ledger", exp_id="family:fcarry", ts=0, alpha=-0.0125, note=families.RELEASE_NOTE)
        self.assertEqual(fleet.strategy_pass(self.db)["registered"], [])
        self.assertIn("alpha_F is not reserved for the family", self.events("family.waiting")[-1]["reasons"])
        with self.assertRaises(lifecycle.LifecycleError):
            families.register_transition(self.db, "E_fcarry__filt_a8", "fcarry", "system:strategy-1")
        self.assertFalse(families.registered(self.db, "fcarry"))
        self.assertEqual(self.family_batches(), [])

    def test_an_unapproved_family_is_skipped_silently(self):
        families.discover_all(self.db)
        self.revive()
        self.touch()
        self.assertEqual(fleet.strategy_pass(self.db)["registered"], [])
        self.assertEqual(self.events("family.waiting"), [])
        self.assertEqual(fleet.strategy_pass(self.db)["families"], {"fcarry": "not approved"})

    def test_an_approved_family_waits_once_while_a_base_instance_is_not_discovered(self):
        """Changed with the 'partial base batch' finding: this test approved before any revival, which approve-family
        now refuses (point 6). An approved family waits when a base instance left DISCOVERED after the approval (here
        `lab transition ... SUPPRESSED`); nothing registers, not even the other two (point 7)."""
        families.discover_all(self.db)
        self.revive()
        self.approve()
        self.touch()
        e = "E_fcarry__floor_a8"
        lifecycle.auto_transition(self.db, e, "SUPPRESSED", "system:cli", "suppressed again after the approval")
        for _ in range(3):
            self.assertEqual(fleet.strategy_pass(self.db)["registered"], [])
        w = self.events("family.waiting")
        self.assertEqual(len(w), 1)
        self.assertIn(f"base instance(s) not DISCOVERED: {e} (SUPPRESSED)", w[0]["reasons"][0])
        self.assertIn("revival comes before approve-family", w[0]["reasons"][0])
        self.assertFalse(families.registered(self.db, "fcarry"))
        self.assertEqual({lifecycle.state(self.db, x) for x in BASE if x != e}, {"DISCOVERED"})


class Graveyard(A3Base):
    """Test 7 at registration: the re-check ignores siblings; covering ignores siblings but blocks a second open family;
    at most 3 open families; the programme stop."""

    def test_a_new_unacknowledged_graveyard_hit_blocks_registration(self):
        self.ready()
        self.grave("L99_new_related", "funding_carry")
        self.assertEqual(fleet.strategy_pass(self.db)["registered"], [])
        self.assertIn("graveyard re-check: L99_new_related not acknowledged in the family file",
                      self.events("family.waiting")[-1]["reasons"])

    def test_the_re_check_and_covering_ignore_siblings(self):
        self.ready()
        self.grave("E_fcarry__zzz_a8", "delta_neutral_funding_carry")      # a rejected member of the family itself
        self.assertEqual(families.registration_block(self.db, FCARRY), [])
        self.assertEqual(sorted(fleet.strategy_pass(self.db)["registered"]), BASE)

    def test_a_second_open_family_on_the_same_tag_is_blocked(self):
        self.ready()
        fleet.strategy_pass(self.db)
        other = copy.deepcopy(FCARRY)
        other["family_id"] = "fcarr2"
        self.db.event("family.approved", "human:anton", None, {"family": "fcarr2", "blobs": families.bound_blobs("x"),
                                                               "thresholds": families.thresholds(),
                                                               "alpha_family": 0.0125, "instances": ["filt"]})
        self.db.append("alpha_ledger", exp_id="family:fcarr2", ts=0, alpha=0.0125, note="A8 reserve")
        why = families.registration_block(self.db, other)
        self.assertTrue(any(w.startswith("open experiment(s) outside the family") and "E_fcarry__filt_a8" in w
                            for w in why), why)

    def test_at_most_three_open_families_and_the_programme_stop(self):
        self.ready()
        for fid in ("faaa", "fbbb", "fccc"):
            self.db.append("transitions", exp_id=f"E_{fid}__x1_a8", ts=0, from_state="DISCOVERED",
                           to_state="REGISTERED", actor="fixture", reason="fixture: registered")
        self.assertIn("3 families are already open: faaa, fbbb, fccc", families.registration_block(self.db, FCARRY))
        self.db.event("family.closed", "system:fixture", None, {"family": "faaa", "outcome": "FUTILE_IN_SAMPLE"})
        self.assertEqual(families.registration_block(self.db, FCARRY), [])
        for fid in ("fbbb", "fccc"):
            self.db.event("family.closed", "system:fixture", None, {"family": fid, "outcome": "UNTESTABLE"})
        why = families.registration_block(self.db, FCARRY)
        self.assertTrue(any("3 families in a row" in w for w in why), why)
        with self.assertRaises(families.FamilyError):                     # and no new approval either
            families.request(self.db, "fcarry", "human:anton", "Anton approves F1 after reading it")

    def test_no_forward_pass_by_mid_2028_stops_the_programme(self):
        """Changed with finding protocol-statistics #2: a PASS counts only as a forward result of the member's cohort
        (recorded by its step, with the cohort id and its hash-matching observe.json); the row this test wrote before
        (no cohort, no artifact) lifted the stop and no longer does."""
        self.assertEqual(families.programme_stop(self.db, ts(2028, 6, 30, 23, 59, 59)), [])
        self.assertTrue(families.programme_stop(self.db, ts(2028, 7, 1)))
        e = "E_fold__x1_a8"
        self.db.append("experiments", exp_id=e, version=1, created_ts=0, mechanism_tag="t", fingerprint="f",
                       spec_json={})
        self.db.append("transitions", exp_id=e, ts=0, from_state=None, to_state="OBSERVATION", actor="fixture",
                       reason="fixture: forward test")
        self.db.event("cohort.fixed", "system:fixture", None, {"family": "fold", "cohort": "fold:fwd202612m12",
                                                              "selected": [e], "not_selected": [], "M": 1})
        art = pipeline.save_artifact(e, "observe", {"window": "fwd202612m12", "fixture": True})
        registry.record_result(self.db, e, "VALIDATION", families.FORWARD_PASS + ": fixture", {}, {}, "system:fixture")
        self.assertTrue(families.programme_stop(self.db, ts(2028, 7, 1)))       # no cohort id, no artifact
        registry.record_result(self.db, e, "VALIDATION", families.FORWARD_PASS + ": fixture",
                               {"cohort": "fold:fwd202612m12"}, {"artifacts": [art]}, "system:fixture")
        self.assertEqual(families.programme_stop(self.db, ts(2028, 7, 1)), [])


class Embargo(A3Base):
    """Test 8 under amendment 9: train3/validation3 spot klines may be fetched before 2026-10-24 00:00 UTC; nothing from
    then until 2026-11-28 00:00 UTC; holdout and forward data only after 2026-11-27."""

    def test_the_rule(self):
        spot, perp, fund = families.SPOT, "binance_um_klines_1h", "binance_um_fundingRate"
        cases = [(ts(2026, 10, 23, 23, 59, 59), spot, "train3", True), (ts(2026, 10, 23), spot, "validation3", True),
                 (ts(2026, 10, 23), perp, "train3", False), (ts(2026, 10, 23), fund, "train3", False),
                 (ts(2026, 10, 23), spot, "holdout", False), (ts(2026, 10, 24), spot, "train3", False),
                 (ts(2026, 11, 27, 23, 59, 59), spot, "train3", False), (ts(2026, 11, 27, 23, 59, 59), spot, "holdout", False),
                 (ts(2026, 11, 28), spot, "train3", True), (ts(2026, 11, 28), perp, "holdout", True),
                 (ts(2026, 11, 28), fund, "fwd202612m12", True)]
        for now, src, split, ok in cases:
            with self.subTest(now=now, src=src, split=split):
                self.assertIs(families.fetch_allowed(src, split, now), ok)
        self.now[0] = ts(2026, 10, 24)
        self.assertFalse(families.fetch_allowed(spot, "train3"))              # the clock is data.CLOCK

    def test_in_the_embargo_nothing_registers_and_one_waiting_event_is_written(self):
        self.ready(files=False)
        self.touch(kinds=("klines", "funding"))                                # spot files missing
        with mock.patch.object(families, "guarded_get") as g:
            for _ in range(3):
                self.assertEqual(fleet.strategy_pass(self.db)["registered"], [])
        g.assert_not_called()
        w = self.events("family.waiting")
        self.assertEqual(len(w), 1)
        self.assertEqual(w[0]["reasons"], [f"720 {families.EMBARGO_REASON}"])
        self.assertEqual(sum(jobs.counts(self.db).values()), 0)
        self.touch(kinds=("spot",))                                            # every file present: it registers
        self.assertEqual(sorted(fleet.strategy_pass(self.db)["registered"]), BASE)

    def test_before_october_24_missing_spot_files_do_not_block_but_perp_files_do(self):
        self.now[0] = ts(2026, 10, 20)
        self.ready(files=False)
        perp = data.expected_paths("ADAUSDT", "train3")["klines"][0][1]
        self.touch(kinds=("klines", "funding"), skip=(perp,))
        self.assertEqual(fleet.strategy_pass(self.db)["registered"], [])
        self.assertEqual(self.events("family.waiting")[-1]["reasons"], [f"1 {families.EMBARGO_REASON}"])
        self.touch(kinds=("klines",))
        self.assertEqual(sorted(fleet.strategy_pass(self.db)["registered"]), BASE)

    def test_from_november_28_it_registers_and_downloads_through_the_guard(self):
        self.now[0] = ts(2026, 11, 28)
        self.ready(files=False)
        self.assertEqual(sorted(fleet.strategy_pass(self.db)["registered"]), BASE)
        calls, fetched = [], []

        def recorder(url, path, get=None):
            self.assertTrue(getattr(get, "guarded", False), url)            # every family fetch is guarded
            calls.append(url)
            get(url)
            return None
        with mock.patch.object(data, "_fetch", recorder), \
                mock.patch.object(families, "_urlopen", lambda url: fetched.append(url) or b"zip"):
            spec = pipeline._spec(self.db, "E_fcarry__filt_a8")
            per = pipeline._download(self.db, "E_fcarry__filt_a8", spec, "train3", "data-1", ("BTCUSDT",))
        self.assertEqual(per, {"BTCUSDT": {"klines": [], "funding": [], "spot": []}})
        self.assertEqual(calls, fetched)
        self.assertEqual(len(calls), 18 * 3)
        self.assertEqual(sum("/data/spot/monthly/klines/BTCUSDT/1h/" in u for u in calls), 18)

    def test_a_screening_job_waits_for_the_embargo_instead_of_failing(self):
        self.queue_on_the_fixture_clock()
        self.now[0] = ts(2026, 10, 20)                                         # registered while spot may be fetched
        self.ready(files=False)
        self.touch(kinds=("klines", "funding"))
        self.assertEqual(sorted(fleet.strategy_pass(self.db)["registered"]), BASE)
        self.now[0] = ts(2026, 10, 25)                                         # the embargo started before the data step
        agent = [a for a in fleet.agents(self.db_path) if a.name == "data-1"][0]
        for _ in BASE:
            agent(self.db)
        for e in BASE:
            j = jobs.get(self.db, f"data|{e}")
            self.assertEqual((j["status"], j["attempts"], j["next_run"]), ("queued", 0, families.EMBARGO_UNTIL), e)
        self.assertEqual(len(self.events("job.deferred")), 3)
        self.assertEqual(self.db.one("SELECT COUNT(*) FROM events WHERE kind IN ('job.retry','job.failed')")[0], 0)
        w = [x for x in self.events("family.waiting") if x["reasons"] == [families.EMBARGO_REASON]]
        self.assertEqual(len(w), 1)                                            # written once, not per job
        self.assertIsNone(jobs.claim(self.db, "data-1", ("data",)))           # nothing runs before 2026-11-28

    def test_the_guard(self):
        url = f"{data.SPOT_BASE}/klines/BTCUSDT/1h/BTCUSDT-1h-2022-01.zip"
        fetched = []
        get = families.guarded_get("train3", fetch=lambda u: fetched.append(u) or b"zip")
        with self.assertRaises(families.Embargoed):
            get(url)                                                           # 2026-11-20: embargo
        self.now[0] = ts(2026, 10, 23)
        self.assertEqual(get(url), b"zip")
        for bad in ("https://example.com/x.zip", f"{data.BASE}/klines/BTCUSDT/1h/BTCUSDT-1h-2022-01.zip"):
            with self.assertRaises(families.Embargoed):
                get(bad)                                                       # other host / perp before 10-24
        self.assertEqual(fetched, [url])

        def gone(u):
            raise urllib.error.HTTPError(u, 404, "not found", None, None)
        url2 = url.replace("2022-01", "2022-02")
        with self.assertRaises(urllib.error.HTTPError):
            families.guarded_get("train3", fetch=gone)(url2)
        self.now[0] = ts(2026, 11, 1)                                          # embargo: a remembered 404 needs no request
        with self.assertRaises(urllib.error.HTTPError):
            families.guarded_get("train3", fetch=lambda u: self.fail("requested again"))(url2)
        self.assertNotIn(url2, [x[2] for x in families.missing(["BTCUSDT"], ("train3",))])

    def test_the_engine_never_retries_a_refused_fetch(self):
        real = self.p[5]
        real.stop()                                                            # the real data._fetch, guarded get
        try:
            with mock.patch("time.sleep", lambda s: self.fail("retried after a refusal")):
                with self.assertRaises(families.Embargoed):
                    data._fetch(f"{data.SPOT_BASE}/klines/X/1h/X-1h-2022-01.zip",
                                os.path.join(self.cache, "spot_klines", "X-1h-2022-01.zip"),
                                families.guarded_get("train3"))
        finally:
            real.start()


class SpotCache(A3Base):
    def test_a_perp_zip_of_the_same_name_is_never_used_as_spot(self):
        """Test 11."""
        perp = os.path.join(self.cache, "klines", "BTCUSDT-1h-2022-01.zip")
        os.makedirs(os.path.dirname(perp))
        open(perp, "wb").close()
        with self.assertRaises(AssertionError):                                # data._fetch raises: no perp reuse
            data.spot_files_for("BTCUSDT", "train3")
        seen = []
        with mock.patch.object(data, "_fetch", lambda url, path, get=None: seen.append((url, path)) or path):
            got = data.spot_files_for("BTCUSDT", "train3")
        self.assertNotIn(perp, got)
        self.assertEqual(len(got), 18)
        self.assertTrue(all(os.path.dirname(p) == os.path.join(self.cache, "spot_klines") for p in got))
        self.assertTrue(all(u.startswith(data.SPOT_BASE + "/klines/BTCUSDT/1h/") for u, _ in seen))
        self.assertEqual(data.expected_paths("BTCUSDT", "train3", spot=True)["spot"], seen)

    def test_spot_files_are_recorded_in_the_same_gateway_access(self):
        self.ready()
        fleet.strategy_pass(self.db)
        e = "E_fcarry__filt_a8"
        lifecycle.auto_transition(self.db, e, "SCREENING", "system:fixture", "screening starts in this test")
        with mock.patch.object(data, "_fetch", lambda url, path, get=None: path if os.path.exists(path) else None):
            pipeline._files(self.db, e, "train3", "data-1")
        acc = self.events("data.accessed")
        self.assertEqual(len(acc), 1)
        self.assertEqual(sum("/spot_klines/" in p for p in acc[0]["paths"]), 30 * 18)
        self.assertEqual(sum("/klines/" in p and "/spot_klines/" not in p for p in acc[0]["paths"]), 30 * 18)
        codes = {r[0] for r in self.db.q("SELECT DISTINCT code_hash FROM datasets WHERE exp_id=?", e)}
        self.assertEqual(codes, {CLEAN["family"]["committed"]})


class Invariants(A3Base):
    """The non-negotiable invariants of the task, pinned once more around the family flow."""

    def test_the_catalogue_is_neither_edited_nor_mutated(self):
        import subprocess
        blob = subprocess.check_output(["git", "hash-object", os.path.join(families.HERE, "lab", "engine",
                                                                           "catalogue.py")], text=True).strip()
        self.assertTrue(blob.startswith("cfa04601fd86"), blob)          # the blob the 3 template approvals bind
        before = {k: id(v) for k, v in catalogue.TEMPLATES.items()}
        snapshot = json.dumps({k: sorted(v) for k, v in catalogue.TEMPLATES.items()}, sort_keys=True)
        out = pipeline.discover_catalogue(self.db)
        self.assertEqual(sorted(e for e, _, _ in out), sorted(catalogue.exp_id(t) for t in catalogue.TEMPLATES))
        self.ready()
        fleet.strategy_pass(self.db)
        spec = pipeline._spec(self.db, "E_fcarry__filt_a8")
        pipeline._tpl(spec), families.template(spec)
        self.assertEqual({k: id(v) for k, v in catalogue.TEMPLATES.items()}, before)
        self.assertEqual(json.dumps({k: sorted(v) for k, v in catalogue.TEMPLATES.items()}, sort_keys=True), snapshot)
        self.assertEqual(len(catalogue.TEMPLATES), 28)
        self.assertFalse([t for t in catalogue.TEMPLATES if "__" in t or "fcarry" in t])

    def test_family_instances_never_take_the_automatic_promotion_path(self):
        from lab import promotion
        self.ready()
        fleet.strategy_pass(self.db)
        e = "E_fcarry__filt_a8"
        for st in ("SCREENING", "OBSERVATION"):
            self.db.append("transitions", exp_id=e, ts=0, from_state=None, to_state=st, actor="fixture",
                           reason="fixture: forward test")
        rid = registry.record_result(self.db, e, "VALIDATION", "PASS (forward test): fixture", {}, {}, "system:fixture")
        self.db.append("transitions", exp_id=e, ts=0, from_state="OBSERVATION", to_state="SCREEN_PASSED",
                       actor="fixture", reason="fixture: forward pass", evidence={"result_id": rid})
        promotion.set_policy(self.db, True, "human:anton", "automatic promotion on in this test")
        with mock.patch.object(promotion, "supervisor_ok", lambda db, now=None: True):
            d = promotion.decide(self.db, e)
        self.assertFalse(d["allowed"])
        self.assertIn("catalogue experiment (pre-registered template)", d["closed"])
        self.assertEqual(lifecycle.state(self.db, e), "SCREEN_PASSED")

    def test_no_forward_paper_observation_or_order_side_effects_and_the_roster_is_unchanged(self):
        from lab import paper
        self.ready()
        fleet.strategy_pass(self.db)
        self.assertEqual(self.db.one("SELECT COUNT(*) FROM events WHERE kind LIKE 'forward.%' OR kind IN "
                                     "('observation.started', 'paper.started')")[0], 0)
        self.assertEqual(self.db.one("SELECT COUNT(*) FROM sim_orders")[0], 0)
        self.assertEqual(len(paper.FORWARD_ACCOUNTS), 10)
        self.assertNotIn("E_fcarry__filt_a8", paper.FORWARD_ACCOUNTS)
        self.assertEqual([(n, e) for n, _, _, _, e, _ in fleet.ROSTER],
                         [("data-1", None), ("discovery-scanner", 3600), ("premium-watch", 60),
                          ("discovery-catalogue", 600), ("strategy-1", 30), ("backtest-1", None),
                          ("backtest-2", None), ("cost-1", None), ("cost-2", None), ("adversarial-1", None),
                          ("adversarial-2", None), ("adversarial-3", None), ("validation-1", None),
                          ("validation-2", None), ("report-1", None), ("paper-1", 60), ("risk-1", 15)])

    def test_mvrv_keeps_its_forward_split(self):
        nov = ts(2026, 11, 1)
        saved = dict(data.SPLITS), dict(data.GATEWAY_SPLIT)
        try:
            self.assertEqual(data.forward_split(nov, 6), "fwd202611")
            self.assertEqual(data.forward_split(nov, 6, tagged=True), "fwd202611m06")
            self.assertEqual(data.forward_split(ts(2026, 12, 1), 12, tagged=True), "fwd202612m12")
            self.assertEqual(data.SPLITS["fwd202611"], ((2026, 11), (2027, 4)))
            self.assertEqual(data.SPLITS["fwd202612m12"], ((2026, 12), (2027, 11)))
            self.assertEqual(data.GATEWAY_SPLIT["fwd202612m12"], "forward")
        finally:
            data.SPLITS.clear(), data.SPLITS.update(saved[0])
            data.GATEWAY_SPLIT.clear(), data.GATEWAY_SPLIT.update(saved[1])

    def test_a_deferred_job_gets_its_attempt_back(self):
        jobs.enqueue(self.db, "data|X", "data", "X", {})
        j = jobs.claim(self.db, "w1", ("data",))
        self.assertFalse(jobs.defer(self.db, "data|X", "w2", "not the owner", families.EMBARGO_UNTIL, now=self.now[0]))
        self.assertTrue(jobs.defer(self.db, "data|X", "w1", "embargo", families.EMBARGO_UNTIL, now=self.now[0]))
        j = jobs.get(self.db, "data|X")
        self.assertEqual((j["status"], j["attempts"], j["next_run"], j["lease_owner"]),
                         ("queued", 0, families.EMBARGO_UNTIL, None))


# ---------- phase A4: the F1 mechanism, the instrument model and the screen (design (C) tests 12-16, 23, 25) ----------
import csv  # noqa: E402
import io  # noqa: E402
import math  # noqa: E402
import random  # noqa: E402
import zipfile  # noqa: E402
from lab import paper_runner, promotion  # noqa: E402
from lab.engine import adversarial, backtest  # noqa: E402
from lab.families import fcarry  # noqa: E402

HOUR, DAY = 3600, 86400
GRIDS = {"carry_filter": FCARRY["instances"][0]["grid"],
         "carry_filter_weekly": FCARRY["instances"][0]["successor"]["grid"],
         "carry_hysteresis": FCARRY["instances"][1]["grid"], "carry_floor": FCARRY["instances"][2]["grid"]}
WEEKLY = ("carry_filter_weekly", "carry_floor")
ZERO = {"taker_fee": 0.0, "half_spread": 0.0, "slippage": 0.0}


def series(days, coins=("AUSDT", "BUSDT", "CUSDT"), start=None, seed=3, interval=8, level=None):
    """Synthetic instrument bars and cost-convention funding (minus the settled rate). The rate accrues per hour at
    `level` per 8 hours, else in 21-day regimes alternating 0.0004 and a daily draw from -0.0002, 0.00005, 0.0001
    (exactly the floor) and 0.0002 per 8 hours; a settlement every `interval` hours pays what accrued since the last."""
    start = start or ts(2022, 1, 1)
    rng = random.Random(seed)
    bars, fund = {}, {}
    for j, s in enumerate(coins):
        bars[s] = [(t, 1.0, 1.0 + rng.gauss(0, 1e-3)) for t in range(start, start + days * DAY, HOUR)]
        lv = [level if level is not None else 0.0004 if (d + 5 * j) // 21 % 2 == 0 else
              rng.choice((-0.0002, 0.00005, 0.0001, 0.0002)) for d in range(days)]
        fund[s] = {start + k * interval * HOUR: -math.fsum(lv[h // 24] / 8 for h in range(k * interval - interval,
                                                                                          k * interval))
                   for k in range(1, days * 24 // interval)}
    return bars, fund


class Mechanism(unittest.TestCase):
    """Test 13: positions change only at 01:00 UTC (Mondays for the weekly rules), use only funding settled before the
    decision, stay flat until the lookback lies inside the window, and the truncation and poison tests are exact for
    all 4 fcarry functions."""

    def test_decisions_at_01_00_and_exact_look_ahead_tests(self):
        bars, fund = series(84)
        for fn, grid in GRIDS.items():
            for p in grid:
                with self.subTest(fn=fn, p=p):
                    f = getattr(fcarry, fn)
                    pos = f(bars, fund, p)
                    on = 0
                    for s, b in bars.items():
                        self.assertEqual(len(pos[s]), len(b))
                        self.assertLessEqual(set(pos[s]), {0.0, 1.0})
                        for i in range(1, len(b)):
                            if pos[s][i] != pos[s][i - 1]:
                                d = datetime.fromtimestamp(b[i][0], timezone.utc)
                                self.assertEqual((d.hour, d.minute), (1, 0))
                                if fn in WEEKLY:
                                    self.assertEqual(d.weekday(), 0)
                        on += sum(pos[s])
                    self.assertGreater(on, 0)                                  # not vacuous
                    self.assertTrue(adversarial.truncation_test_xs(f, bars, fund, p, 20)["ok"])
                    self.assertTrue(adversarial.poison_test_xs(f, bars, fund, p)["ok"])

    def test_only_funding_settled_before_the_decision_counts(self):
        start = ts(2022, 1, 3)                                                 # a Monday
        bars, fund = series(30, coins=("AUSDT",), start=start, level=0.00005)  # APR 0.055: every rule is flat
        T = start + 21 * DAY + HOUR                                            # Monday 01:00
        i = next(k for k, b in enumerate(bars["AUSDT"]) if b[0] == T)
        held = slice(0, i + 24)                                                # bars up to the next decision
        for fn, grid in GRIDS.items():
            with self.subTest(fn=fn):
                f, p = getattr(fcarry, fn), grid[0]
                base = f(bars, fund, p)["AUSDT"]
                self.assertEqual(set(base), {0.0})
                at = {"AUSDT": {**fund["AUSDT"], T: -1.0}}                      # settles at the decision: unknown
                self.assertEqual(f(bars, at, p)["AUSDT"][held], base[held])
                before = {"AUSDT": {**fund["AUSDT"], T - HOUR: -1.0}}           # settled at 00:00, before 01:00
                if fn == "carry_floor":                                         # Monday 00:00 is an incomplete day
                    self.assertEqual(f(bars, before, p)["AUSDT"][held], base[held])
                    floor = {"AUSDT": {t: (-0.0001 if t >= start + 7 * DAY else v) for t, v in fund["AUSDT"].items()}}
                    got = f(bars, floor, p)["AUSDT"]                            # the 14 days before T at the floor
                else:
                    got = f(bars, before, p)["AUSDT"]
                self.assertEqual((got[i - 1], got[i]), (0.0, 1.0))             # the 00:00 bar is not held

    def test_flat_until_the_lookback_lies_inside_the_window(self):
        bars, fund = series(40, level=0.0004)                                  # always above every threshold
        first = {"carry_filter": ts(2022, 1, 8, 1), "carry_hysteresis": ts(2022, 1, 8, 1),
                 "carry_filter_weekly": ts(2022, 1, 10, 1), "carry_floor": ts(2022, 1, 17, 1)}
        for fn, grid in GRIDS.items():
            for p in grid:
                with self.subTest(fn=fn, p=p):
                    b, pos = bars["AUSDT"], getattr(fcarry, fn)(bars, fund, p)["AUSDT"]
                    self.assertEqual([x[0] for x, q in zip(b, pos) if q == 1.0][0], first[fn])
                    self.assertEqual(pos, [1.0 if x[0] >= first[fn] else 0.0 for x in b])
        late = {s: b[5 * 24:] for s, b in bars.items()}                        # a window that starts 5 days later
        pos = fcarry.carry_filter(late, fund, GRIDS["carry_filter"][0])["AUSDT"]
        self.assertEqual(late["AUSDT"][pos.index(1.0)][0], ts(2022, 1, 13, 1))  # no history from before the window

    def test_interval_free_sums_and_thresholds_reached_exactly(self):
        """The same accrued funding settled every 8, 4 or 2 hours gives the same positions: the 7-day windows sum what
        was settled (never a mean per settlement). The floor's calendar-day sums are interval-free at a steady rate."""
        for fn, grid in GRIDS.items():
            for level in ((0.0001, 0.0003) if fn == "carry_floor" else (None, 0.0001, 0.0003)):
                for p in grid:
                    ref = getattr(fcarry, fn)(*series(84, level=level), p)
                    for interval in (4, 2):
                        with self.subTest(fn=fn, level=level, p=p, interval=interval):
                            self.assertEqual(getattr(fcarry, fn)(*series(84, interval=interval, level=level), p), ref)
        for interval in (8, 2):                                                 # exactly the 0.01 %/8h floor
            bars, fund = series(40, coins=("AUSDT",), level=0.0001, interval=interval)
            for f, p, want in ((fcarry.carry_filter, {"lookback_days": 7, "enter_apr": 0.1095}, 1.0),
                               (fcarry.carry_filter, {"lookback_days": 7, "enter_apr": 0.219}, 0.0),
                               (fcarry.carry_floor, {"days": 14, "q": 0.95}, 1.0)):
                self.assertEqual(f(bars, fund, p)["AUSDT"][-1], want, (interval, p))

    def test_hysteresis_keeps_the_position_between_its_thresholds(self):
        start, lv = ts(2022, 1, 1), (0.0003, 0.0001, 0.00003, -0.0001)        # APR 0.33, 0.11, 0.03, -0.11
        bars = {"AUSDT": [(t, 1.0, 1.0) for t in range(start, start + 80 * DAY, HOUR)]}
        fund = {"AUSDT": {start + d * DAY + h * HOUR: -lv[d // 20] for d in range(80) for h in (0, 8, 16)}}
        idx = {b[0]: i for i, b in enumerate(bars["AUSDT"])}
        at = {k: idx[start + k * DAY + HOUR] for k in (19, 39, 59, 79)}
        for exit_apr, want in ((0.0, (1.0, 1.0, 1.0, 0.0)), (0.1095, (1.0, 1.0, 0.0, 0.0))):
            pos = fcarry.carry_hysteresis(bars, fund, {"lookback_days": 7, "exit_apr": exit_apr})["AUSDT"]
            self.assertEqual(tuple(pos[at[k]] for k in (19, 39, 59, 79)), want, exit_apr)

    def test_attribution(self):
        m = {"funding": -0.05, "fees": 0.01, "spread": 0.005, "slippage": 0.005, "gross_total": 0.02}
        a = fcarry.attribution(m)
        self.assertEqual((a["funding_income"], round(a["costs"], 12), a["gates"]),
                         (0.05, 0.02, {"funding income - costs > 0": True, "gross ratio P&L <= funding income": True}))
        self.assertFalse(fcarry.attribution({**m, "fees": 0.05})["gates"]["funding income - costs > 0"])
        self.assertFalse(fcarry.attribution({**m, "gross_total": 0.06})["gates"]["gross ratio P&L <= funding income"])
        self.assertFalse(fcarry.attribution({"bars": 0})["gates"]["funding income - costs > 0"])   # no rows
        self.assertEqual(families.attribution({"family": "fcarry"}, m), a)


def _pzip(path, header, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(header)
    w.writerows(rows)
    with zipfile.ZipFile(path, "w") as z:
        z.writestr(os.path.basename(path).replace(".zip", ".csv"), buf.getvalue())


KL = ["open_time", "open", "high", "low", "close", "volume", "close_time"]
FR = ["calc_time", "funding_interval_hours", "last_funding_rate"]


def write_pairs(root, symbols, years=(2022, 2023), seed=5, rate=None, drop_spot=(), span=None):
    """Monthly perp kline, spot kline (open times in microseconds, as Binance spot files since 2025) and funding zips in
    the Binance layout. The perps fall (buy-and-hold loses), spot follows the perp within about 2 bp, and the settled
    funding alternates 21-day regimes of 0.03 %/8h and -0.01 %/8h, shifted 3 days per coin (or is `rate`). `span`
    (start, end) replaces the whole years."""
    rng = random.Random(seed)
    a, b = span or (ts(years[0], 1, 1), ts(years[-1] + 1, 1, 1))
    out = {}
    for j, sym in enumerate(symbols):
        px, perp, spot, fund = 100.0, {}, {}, {}
        for t in range(a, b, HOUR):
            o = px
            px *= 1 + rng.gauss(-0.00004, 0.003)
            d = datetime.fromtimestamp(t, timezone.utc)
            perp.setdefault((d.year, d.month), []).append([t * 1000, o, max(o, px), min(o, px), px, 1,
                                                           t * 1000 + 3599999])
            so, sc = o * (1 + rng.gauss(0, 0.0002)), px * (1 + rng.gauss(0, 0.0002))
            if t not in drop_spot:
                spot.setdefault((d.year, d.month), []).append([t * 10 ** 6, so, max(so, sc), min(so, sc), sc, 1,
                                                               t * 10 ** 6 + 3599999999])
            if t % (8 * HOUR) == 0:
                r = rate if rate is not None else 0.0003 if ((t - a) // DAY + 3 * j) // 21 % 2 == 0 else -0.0001
                fund.setdefault((d.year, d.month), []).append([t * 1000, 8, r])
        out[sym] = {"klines": [], "funding": [], "spot": []}
        for (y, m) in perp:
            for kind, folder, name, header, rows in (
                    ("klines", "klines", f"{sym}-1h-{y}-{m:02d}.zip", KL, perp[(y, m)]),
                    ("spot", "spot_klines", f"{sym}-1h-{y}-{m:02d}.zip", KL, spot.get((y, m), [])),
                    ("funding", "funding", f"{sym}-fundingRate-{y}-{m:02d}.zip", FR, fund[(y, m)])):
                p = os.path.join(root, folder, name)
                _pzip(p, header, rows)
                out[sym][kind].append(p)
    return out


class Transform(unittest.TestCase):
    """Test 12: the spot_perp_ratio instrument model."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="labfamA4t")

        def no_fetch(url, path, get=None):
            raise AssertionError(f"a family test tried to fetch {url}")
        self.p = [mock.patch.dict(data.SPLITS, {"t1": ((2022, 1), (2022, 1))}),
                  mock.patch.object(data, "_fetch", no_fetch)]
        for p in self.p:
            p.start()
        self.spec = {"family": "fcarry", "function": "carry_filter", "instrument_model": "spot_perp_ratio",
                     "min_symbols": 1, "protocol_version": 3}

    def tearDown(self):
        for p in reversed(self.p):
            p.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def files(self, **kw):
        per = write_pairs(self.tmp, ("AUSDT",), years=(2022,), **kw)
        return {"AUSDT": {k: v[:1] for k, v in per["AUSDT"].items()}}           # January 2022 only

    def test_ratio_series_and_funding_in_the_cost_convention(self):
        per = self.files(rate=0.0001)
        bars, funding, dups, fd = families.transform(self.spec, per, "t1")
        b, perp = bars["AUSDT"], fd.perp["AUSDT"]
        spot, _, _ = data.load({"klines": per["AUSDT"]["spot"], "funding": []}, "t1")
        self.assertEqual((len(b), len(perp), len(spot), dups["AUSDT"]), (744, 744, 744, 0))   # microseconds parse
        self.assertEqual([x[0] for x in b], [x[0] for x in perp])
        for i in range(1, len(b)):
            rs, rp = spot[i][2] / spot[i - 1][2] - 1, perp[i][2] / perp[i - 1][2] - 1
            self.assertAlmostEqual(b[i][2] / b[i - 1][2] - 1, rs - rp, delta=1e-5)
        self.assertEqual(set(funding["AUSDT"].values()), {-0.0001})
        self.assertEqual(set(fd.funding["AUSDT"].values()), {0.0001})
        rows = backtest.apply_costs(backtest.gross(b, [1.0] * len(b)), funding["AUSDT"], ZERO)
        settled = sum(1 for t in funding["AUSDT"] if t > b[0][0])
        self.assertEqual(settled, 92)
        self.assertAlmostEqual(sum(r[7] for r in rows) - sum(r[2] for r in rows), 0.0001 * settled, places=12)
        with self.assertRaises(families.FamilyError):                         # spot_delivery_ratio is F2's model
            families.transform({**self.spec, "instrument_model": "spot_future_ratio"}, per, "t1")

    def test_a_missing_spot_hour_lowers_coverage_until_the_coin_is_excluded(self):
        a = ts(2022, 1, 1)
        for n, excluded in ((7, []), (8, ["AUSDT"])):                            # 737/744 >= 0.99 > 736/744
            with self.subTest(missing=n):
                per = self.files(drop_spot={a + 40 * HOUR * k for k in range(1, n + 1)})
                bars, _, dups, _ = families.transform(self.spec, per, "t1")
                q, ex, enough = pipeline._quality(bars, "t1", dups, self.spec)
                self.assertEqual((len(bars["AUSDT"]), ex, enough), (744 - n, excluded, not excluded))


SIX = ("BNBUSDT", "XRPUSDT", "DOGEUSDT", "ADAUSDT", "LINKUSDT", "LTCUSDT")


class Screen(A3Base):
    """A synthetic end-to-end screen of one fcarry instance through data -> backtest -> cost -> adversarial ->
    validate -> report: six coins of synthetic spot, perp and funding files (min_symbols 5 in this test), the real
    registration path, and data._fetch raising for any file that is not on disk (tests 14, 15 and 16). The family file
    is cut to the screened instance (a one-instance test family): the base batch registers only when every approved
    base instance is DISCOVERED (amendment 8 point 7), so reviving one of three no longer gives a batch of one."""
    market = None

    @classmethod
    def setUpClass(cls):
        cls.market = tempfile.mkdtemp(prefix="labfamA4m")
        write_pairs(cls.market, SIX)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.market, ignore_errors=True)

    def setUp(self):
        super().setUp()
        real, self.only = families.load, "filt"

        def small(path_or_fid):
            fam = real(path_or_fid)
            fam["universe"]["min_symbols"] = 5
            fam["instances"] = [i for i in fam["instances"] if i["id"] == self.only]     # a one-instance family
            return fam

        def disk_only(url, path, get=None):
            if os.path.exists(path):
                return path
            raise AssertionError(f"a family test tried to fetch {url}")
        self.p4 = [mock.patch.object(data, "CACHE", self.market), mock.patch.object(data, "UNIVERSE_30_V3", SIX),
                   mock.patch.object(data, "_fetch", disk_only), mock.patch.object(families, "load", small),
                   mock.patch.object(pipeline, "PLACEBO_N", 20)]
        for p in self.p4:
            p.start()

    def tearDown(self):
        for p in reversed(self.p4):
            p.stop()
        super().tearDown()

    def screen(self, iid="filt"):
        e, self.only = families.exp_id("fcarry", iid), iid
        families.discover_all(self.db)
        self.revive([e])                                                       # the only base instance: a batch of one
        self.approve()
        self.assertEqual(fleet.strategy_pass(self.db)["registered"], [e])
        ag = [a for a in fleet.agents(self.db_path) if a.kinds]
        for _ in range(50):
            for a in ag:
                a(self.db)
            c = jobs.counts(self.db)
            if not (c["queued"] or c["running"] or c["blocked"]):
                break
        self.assertEqual((c["failed"], c["done"]), (0, 6), c)
        return e

    def no_cohort_side_effects(self):
        self.assertEqual(self.events("observation.started"), [])
        self.assertEqual(self.db.q("SELECT job_id FROM jobs WHERE kind='observe'"), [])
        self.assertEqual(self.db.one("SELECT COUNT(*) FROM events WHERE kind LIKE 'forward.%' OR "
                                     "kind='paper.started'")[0], 0)
        self.assertIsNone(self.db.one("SELECT 1 FROM transitions WHERE to_state='SCREEN_PASSED'"))

    def test_a_regime_timed_instance_passes_the_filter_into_observation(self):
        snapshot = json.dumps({k: sorted(v) for k, v in catalogue.TEMPLATES.items()}, sort_keys=True)
        e = self.screen()
        res = self.db.one("SELECT label, verdict FROM results WHERE exp_id=?", e)
        self.assertEqual(lifecycle.state(self.db, e), "OBSERVATION", res["verdict"])
        self.assertEqual(res["label"], "EXPLORATORY")
        self.assertTrue(res["verdict"].startswith("OBSERVE (family forward test)"), res["verdict"])
        cost, adv, val = (pipeline.frozen_artifact(self.db, e, n) for n in ("cost", "adversarial", "validate"))
        self.assertFalse(cost["rejected_early"])
        self.assertTrue(adv["pre_validation_ok"])
        self.assertLess(adv["placebo"]["p"], 0.10)                              # timed: the placebo loses
        self.assertEqual([k for k, ok in val["gates"].items() if not ok and k != pipeline.DSR_GATE], [])
        self.assertIsNotNone(val["dsr"])                                       # recorded, decides nothing
        self.assertEqual(val["trials_counted"], 2)
        att = val["attribution"]
        self.assertGreater(att["funding_income"], att["costs"])
        self.assertLessEqual(att["gross_ratio_pnl"], att["funding_income"])
        self.assertTrue({"mechanism attribution: funding income - costs > 0",
                         "mechanism attribution: gross ratio P&L <= funding income"} <= set(val["gates"]))
        # test 16: the benchmark is the perps' buy-and-hold with the catalogue's costs, not the ratio series
        perp, raw = {}, {}
        for s in SIX:
            perp[s], raw[s], _ = data.load(data.files_for(s, "train3"), "train3")
        want = json.loads(json.dumps(pipeline._strip(pipeline._benchmark(perp, raw, catalogue.COSTS)), default=str))
        self.assertEqual(cost["benchmark"], want)
        self.assertLess(cost["benchmark"]["net_sharpe_ann"], 0)
        # the gateway saw the spot files with the perp files, under the family blob; validation was read once screened
        paths = [r[0] for r in self.db.q("SELECT path FROM datasets WHERE exp_id=? AND split='dev'", e)]
        self.assertEqual(sum("/spot_klines/" in p for p in paths), 6 * 18)
        self.assertEqual({r[0] for r in self.db.q("SELECT DISTINCT code_hash FROM datasets WHERE exp_id=?", e)},
                         {CLEAN["family"]["committed"]})
        self.assertTrue(self.db.one("SELECT 1 FROM datasets WHERE exp_id=? AND split='validation'", e))
        self.no_cohort_side_effects()
        self.assertEqual(json.dumps({k: sorted(v) for k, v in catalogue.TEMPLATES.items()}, sort_keys=True), snapshot)

    def test_a_constant_exposure_instance_fails_the_placebo_without_reading_validation_data(self):
        def always(b, f, p, fit=None, volume_by=None, extra=None):
            return {s: [1.0] * len(x) for s, x in b.items()}
        with mock.patch.object(fcarry, "carry_filter", always):
            e = self.screen()
        adv = pipeline.frozen_artifact(self.db, e, "adversarial")
        self.assertEqual(adv["placebo"]["p"], 1.0)
        self.assertEqual(adv["pre_validation_failed"], [f"train placebo p < {catalogue.PLACEBO_P_MAX}"])
        self.assertEqual(lifecycle.state(self.db, e), "REJECTED")
        verdict = self.db.one("SELECT verdict FROM results WHERE exp_id=?", e)[0]
        self.assertTrue(verdict.startswith("REJECTED before validation (no validation data read)"), verdict)
        self.assertIsNone(self.db.one("SELECT 1 FROM datasets WHERE exp_id=? AND split='validation'", e))
        self.no_cohort_side_effects()


class Routing(A3Base):
    """Test 15 at the report step: a DSR pass and a failure on DSR alone both go to OBSERVATION, never SCREEN_PASSED; an
    attribution failure is REJECTED; no observation.started and no observe job (the cohort writes them, phase A5)."""
    OK = {"net_mean_daily > 0": True, "one-sided 90% lower bound > 0": True, "net Sharpe > buy-and-hold": True,
          "net total > 0 at 2x costs": True, pipeline.DSR_GATE: True, "adversarial checks pass": True,
          "validation data quality": True, "mechanism attribution: funding income - costs > 0": True,
          "mechanism attribution: gross ratio P&L <= funding income": True}

    def report(self, e, gates, dsr):
        lifecycle.auto_transition(self.db, e, "SCREENING", "system:fixture", "screening starts in this test")
        net = {"net_sharpe_ann": 2.0, "gross_sharpe_ann": 1.0, "net_total": 0.05}
        pipeline.save_artifact(e, "cost", {"variants": [{"variant": 0, "params": {}, "net": net, "net_2x_costs": net}],
                                           "benchmark": {"net_sharpe_ann": -1.0}, "selected": 0,
                                           "rejected_early": False})
        pipeline.save_artifact(e, "adversarial", {"ok": True, "pre_validation_ok": True, "placebo": {"p": 0.0}})
        pipeline.save_artifact(e, "validate", {"metrics": net, "benchmark": net, "dsr": dsr, "gates": gates})
        return pipeline.step_report(self.db, {"exp_id": e}, "report-1")

    def test_a_family_instance_never_goes_to_screen_passed(self):
        self.ready()
        fleet.strategy_pass(self.db)
        cases = (("E_fcarry__filt_a8", self.OK, 0.99, "OBSERVATION"),
                 ("E_fcarry__floor_a8", {**self.OK, pipeline.DSR_GATE: False}, 0.4, "OBSERVATION"),
                 ("E_fcarry__hyst_a8", {**self.OK, "mechanism attribution: funding income - costs > 0": False}, 0.99,
                  "REJECTED"))
        for e, gates, dsr, want in cases:
            with self.subTest(e):
                out = self.report(e, gates, dsr)
                self.assertEqual((out["state"], lifecycle.state(self.db, e)), (want, want))
                self.assertTrue(out["verdict"].startswith("OBSERVE (family forward test)" if want == "OBSERVATION"
                                                          else "REJECTED at validation: failed mechanism attribution"),
                                out["verdict"])
        self.assertEqual(self.events("observation.started"), [])
        self.assertEqual(self.db.q("SELECT job_id FROM jobs WHERE kind='observe'"), [])
        self.assertIsNone(self.db.one("SELECT 1 FROM transitions WHERE to_state='SCREEN_PASSED'"))

    def test_the_benchmark_uses_the_perps_and_catalogue_costs(self):
        """Test 16 on the helpers: the benchmark takes the FamilyData perps, _drop drops a coin from them too, and the
        mechanism function never sees FamilyData. A catalogue spec keeps its own benchmark call."""
        bars, fund = series(30, coins=("AUSDT", "BUSDT"))
        perp = {s: [(t, 100 + 0.1 * i, 100 + 0.1 * (i + 1)) for i, (t, _, _) in enumerate(b)] for s, b in bars.items()}
        raw = {s: {t: -v for t, v in f.items()} for s, f in fund.items()}
        spec = {"family": "fcarry", "function": "carry_filter",
                "costs": {k: FCARRY["costs"][k] for k in ("taker_fee", "half_spread", "slippage")}}
        fd = families.FamilyData({s: list(b) for s, b in perp.items()}, {s: dict(f) for s, f in raw.items()})
        got = pipeline._bench(bars, fund, spec, fd)
        self.assertEqual(got, pipeline._benchmark(perp, raw, catalogue.COSTS))
        self.assertNotEqual(got["net_total"], pipeline._benchmark(bars, fund, spec["costs"])["net_total"])
        calls = []
        with mock.patch.object(pipeline, "_benchmark", lambda *a: calls.append(a) or {}):
            pipeline._bench(bars, fund, {"costs": catalogue.COSTS}, {"volume": {}})
        self.assertEqual(calls, [(bars, fund, catalogue.COSTS)])
        seen = []
        with mock.patch.object(fcarry, "carry_filter",
                               lambda b, f, p, fit=None, volume_by=None, extra=None: seen.append((volume_by, extra))
                               or {s: [0.0] * len(x) for s, x in b.items()}):
            pipeline._positions(pipeline._tpl(spec), bars, fund, GRIDS["carry_filter"][0], None, fd)
        self.assertEqual(seen, [(None, None)])
        pipeline._drop(bars, fund, fd, ["BUSDT"], spec)
        self.assertEqual((sorted(bars), sorted(fd.perp), sorted(fd.funding)), (["AUSDT"], ["AUSDT"], ["AUSDT"]))


class PaperAndPromotion(A3Base):
    def test_run_one_on_a_family_instance_is_unsupported_and_trades_nothing(self):
        """Test 25."""
        self.ready()
        fleet.strategy_pass(self.db)
        e = "E_fcarry__filt_a8"

        def no_market(*a, **k):
            raise AssertionError("no market data is read for a family instance")
        for _ in range(2):
            for ledger in (None, "SHADOW_" + e):
                out = paper_runner.run_one(self.db, e, no_market, ts(2026, 11, 20), ledger=ledger)
                self.assertEqual(out["status"], "unsupported")
        self.assertEqual(len(self.events("paper.unsupported")), 2)               # once per ledger
        self.assertEqual(self.db.one("SELECT COUNT(*) FROM events WHERE kind='paper.started'")[0], 0)
        self.assertEqual(self.db.one("SELECT COUNT(*) FROM sim_orders")[0], 0)

    def test_a_validated_family_instance_waits_even_with_autopromote_on(self):
        """Test 23 for the second policy edge: no live spot feed and no catalogue template, so it waits."""
        self.ready()
        fleet.strategy_pass(self.db)
        e = "E_fcarry__floor_a8"
        for st in ("SCREENING", "OBSERVATION", "SCREEN_PASSED", "VALIDATION"):
            self.db.append("transitions", exp_id=e, ts=0, from_state=None, to_state=st, actor="fixture",
                           reason="fixture: the path to a holdout")
        rid = registry.record_result(self.db, e, "VALIDATION", "PASS (holdout): fixture", {}, {}, "system:fixture")
        self.db.append("transitions", exp_id=e, ts=0, from_state="VALIDATION", to_state="VALIDATED", actor="fixture",
                       reason="fixture: holdout passed", evidence={"result_id": rid})
        promotion.set_policy(self.db, True, "human:anton", "automatic promotion on in this test")
        with mock.patch.object(promotion, "supervisor_ok", lambda db, now=None: True):
            d = promotion.decide(self.db, e)
        self.assertFalse(d["allowed"])
        self.assertTrue({"catalogue experiment (pre-registered template)",
                         "paper runner has live data for this template"} <= set(d["closed"]), d["closed"])
        self.assertEqual(lifecycle.state(self.db, e), "VALIDATED")
        self.assertTrue({"spot", "delivery"} <= promotion.LIVE_UNSUPPORTED)


# ---------- phase A5: successors, cohort, forward test, MVRV and amendment 7 safety (design (C) tests 17-22, 26-28) ----
import glob  # noqa: E402
from lab import command, paper  # noqa: E402
from tests.lab_fixtures import frozen  # noqa: E402

NET = {"net_sharpe_ann": 2.0, "gross_sharpe_ann": 1.0, "net_total": 0.05, "fees": 0.01, "spread": 0.002,
       "slippage": 0.002, "funding": -0.03}
F, L, H = BASE                                    # filt, floor, hyst
S = "E_fcarry__filt_w_a8"                         # filt's pre-enumerated successor
LAG = data.FORWARD_LAG_S
FWD_IDS = {"E_vol_managed_long_p1", "E_day_of_week_p1", "E_hour_of_day_p1", "E_funding_contrarian_p1",
           "E_daily_reversal_p1", "E_xs_momentum_p2", "E_xs_max_lottery_p2", "E_xs_low_volatility_p2",
           "E_xs_betting_against_beta_p2", "E_supply_dilution_p3"}            # amendment 7 section 2 (N = 10)


class A5Base(A3Base):
    """A registered fcarry family and a fixture screen: frozen data/backtest/cost/adversarial/validate artifacts,
    hash-recorded the way a finished job records them, then the real report step."""

    def register(self):
        self.ready()
        self.assertEqual(sorted(fleet.strategy_pass(self.db)["registered"]), BASE)

    def screened(self, e, observe=True, sharpe=2.0, early=False, data_ok=True, funding=-0.03, params=None):
        lifecycle.auto_transition(self.db, e, "SCREENING", "system:fixture", "screening starts in this test")
        net = {**NET, "net_sharpe_ann": sharpe, "funding": funding}
        frozen(self.db, e, "data", {"ok": data_ok})
        frozen(self.db, e, "backtest", {"variants": [{"variant": 0, "params": params or {}, "fit": None,
                                                      "positions": {}}]})
        frozen(self.db, e, "cost", {"variants": [{"variant": 0, "params": params or {}, "net": net,
                                                  "net_2x_costs": net}], "benchmark": {"net_sharpe_ann": -1.0},
                                    "selected": 0, "rejected_early": early,
                                    "early_reasons": ["train net Sharpe > 0"] if early else []})
        gates = {**Routing.OK, pipeline.DSR_GATE: False, "validation data quality": data_ok}
        if not observe:
            gates["net Sharpe > buy-and-hold"] = False
        frozen(self.db, e, "adversarial", {"skipped": "rejected at cost check"} if early else
               {"ok": True, "pre_validation_ok": True, "placebo": {"p": 0.0}})
        frozen(self.db, e, "validate", {"skipped": "rejected at the train gate"} if early else
               {"metrics": net, "benchmark": NET, "dsr": 0.3, "gates": gates})
        return pipeline.step_report(self.db, {"exp_id": e}, "report-1")

    def ledger(self):
        return [(r["exp_id"], round(r["alpha"], 10), r["note"]) for r in self.db.q(
            "SELECT exp_id, alpha, note FROM alpha_ledger WHERE note LIKE 'A8 %' AND alpha != 0 ORDER BY id")]

    def status(self):
        return fleet.strategy_pass(self.db)["families"]["fcarry"]


class Lineage(A5Base):
    """Test 17: a successor registers only when its parent's frozen cost.json meets the trigger; never from validation
    numbers, never after the cohort is fixed, no grandchild; untriggered successors are SUPPRESSED at the close."""
    INST = families.instances(FCARRY)[1][0]

    def parent_cost(self, early, funding=-0.005):
        if lifecycle.state(self.db, F) == "REGISTERED":
            lifecycle.auto_transition(self.db, F, "SCREENING", "system:fixture", "screening starts in this test")
        return frozen(self.db, F, "cost", {"variants": [{"variant": 0, "net": {**NET, "funding": funding}}],
                                           "selected": 0, "rejected_early": early})

    def test_a_successor_registers_only_from_its_parents_frozen_cost_json(self):
        self.register()
        self.assertEqual(families.trigger_state(self.db, self.INST, F)[0], "pending")
        self.assertEqual(fleet.strategy_pass(self.db)["registered"], [])
        self.parent_cost(early=False)                                         # the parent passed the train gate
        self.assertEqual(families.trigger_state(self.db, self.INST, F)[0], "not met")
        self.assertEqual(fleet.strategy_pass(self.db)["registered"], [])
        self.parent_cost(early=True, funding=-0.03)                          # costs 0.014 below income 0.03
        self.assertEqual(families.trigger_state(self.db, self.INST, F)[0], "not met")
        self.parent_cost(early=True)                                          # costs 0.014 above income 0.005
        path = os.path.join(pipeline.ARTIFACTS, F, "cost.json")
        with open(path, "rb") as f:
            raw = f.read()
        with open(path, "wb") as f:
            f.write(raw + b" ")                                               # altered after it was recorded
        st, why = families.trigger_state(self.db, self.INST, F)
        self.assertEqual(st, "not met")
        self.assertIn("fails closed", why)
        self.assertEqual(fleet.strategy_pass(self.db)["registered"], [])
        with open(path, "wb") as f:
            f.write(raw)
        frozen(self.db, F, "validate", {"metrics": NET, "gates": {}})          # never read by a trigger
        seen, real = [], pipeline.frozen_artifact
        with mock.patch.object(pipeline, "frozen_artifact", lambda db, e, n: seen.append((e, n)) or real(db, e, n)):
            self.assertEqual(fleet.strategy_pass(self.db)["registered"], [S])
        self.assertEqual({n for e, n in seen if e == F}, {"cost"})
        b = self.family_batches()[-1]
        self.assertEqual((b["exp_ids"], b["successor_of"], b["family"], b["amendment"]), ([S], F, "fcarry", 8))
        tr = self.db.one("SELECT evidence FROM transitions WHERE exp_id=? AND to_state='REGISTERED'", S)
        self.assertEqual(json.loads(tr["evidence"])["family_approval_event"], families.approval(self.db, "fcarry"))
        spec = pipeline._spec(self.db, S)
        self.assertEqual((spec["parent"], spec["function"], spec["template"]),
                         ("filt", "carry_filter_weekly", "fcarry__filt_w"))
        self.assertEqual(jobs.get(self.db, f"validate|{S}")["depends_on"], [f"adversarial|{S}"])
        self.assertEqual([tuple(r) for r in self.db.q("SELECT alpha, note FROM alpha_ledger WHERE exp_id=?", S)],
                         [(0.0, "A8 in-sample filter")])
        self.assertEqual(fleet.strategy_pass(self.db)["registered"], [])          # once

    def test_never_from_validation_never_after_the_cohort_and_no_grandchild(self):
        self.register()
        self.parent_cost(early=True)
        frozen(self.db, F, "validate", {"dsr": 0.99})
        on_validate = {**self.INST, "trigger": {"artifact": "validate", "all": ["dsr >= 0"]}}
        self.assertEqual(families.trigger_state(self.db, on_validate, F)[0], "not met")
        self.assertTrue(any("frozen training artifact" in p for p in
                            problems_of(instances__0__successor__trigger__artifact="validate")))
        self.assertTrue(any("cannot parse" in p for p in
                            problems_of(instances__0__successor__trigger__all=["rejected_early == true; rm"])))
        self.db.event("cohort.fixed", "system:fixture", None, {"family": "fcarry", "cohort": "fcarry:fixture",
                                                              "members": BASE, "selected": [], "not_selected": [],
                                                              "M": 0})
        self.assertEqual(fleet.strategy_pass(self.db)["registered"], [])
        self.assertIn(f"{S}: the family cohort is fixed: successors register only before (point 9)",
                      self.events("family.waiting")[-1]["reasons"])
        self.assertEqual(lifecycle.state(self.db, S), "SUPPRESSED")          # not registered before the cohort
        nested = copy.deepcopy(FCARRY)
        nested["instances"][0]["successor"]["successor"] = dict(nested["instances"][0]["successor"], id="filt_ww")
        self.assertEqual([i["id"] for i, _ in families.instances(nested)], ["filt", "filt_w", "hyst", "floor"])
        self.assertEqual(families.validate(nested), [])                     # a grandchild is never enumerated

    def test_the_cohort_waits_for_a_triggered_successor_until_it_has_a_result(self):
        self.register()
        self.screened(F, early=True, funding=-0.005)                         # rejected at train: triggered
        for e in (L, H):
            self.screened(e)
        self.assertEqual(families.pass_(self.db)["fcarry"],                     # not registered yet: the cohort waits
                         f"waiting for successor(s) that can still register: {S}")
        self.assertIsNone(families.cohort(self.db, "fcarry"))
        self.assertEqual(fleet.strategy_pass(self.db)["registered"], [S])
        self.assertEqual(self.status(), "screening: 3 of 4 registered members have a result")
        self.screened(S, sharpe=0.5)
        self.assertTrue(self.status().startswith("forward test: cohort fcarry:fwd202612m12, M 3"))
        self.assertEqual(families.cohort(self.db, "fcarry")["selected"], [L, H, S])

    def test_untriggered_successors_are_suppressed_when_the_cohort_closes(self):
        self.register()
        for e in BASE:
            self.screened(e, observe=e != H)                                  # filt passed train: not triggered
        self.assertTrue(self.status().startswith("forward test"))
        sup = self.db.one("SELECT actor, reason FROM transitions WHERE exp_id=? ORDER BY id DESC LIMIT 1", S)
        self.assertEqual((lifecycle.state(self.db, S), sup["actor"]), ("SUPPRESSED", "system:strategy-1"))
        self.assertIn("a successor registers only before (amendment 8 point 9)", sup["reason"])


class Cohort(A5Base):
    """Test 18: the cohort closes only after every member has a result and no trigger is open; cohort.fixed holds M <= 3
    by validation net Sharpe, alpha_i = alpha_F / M and the windows fwdYYYYMMm12 / m06 from 2026-12-01; the alpha_ledger
    moves alpha_F to the instances (M >= 1) or releases it (M = 0, FUTILE_IN_SAMPLE or UNTESTABLE)."""

    def test_the_cohort_waits_for_every_result_and_trigger_then_fixes_m_alpha_and_windows(self):
        self.register()
        self.screened(F, sharpe=1.5)
        self.screened(L, sharpe=2.5)
        self.assertEqual(self.status(), "screening: 2 of 3 registered members have a result")
        self.assertIsNone(families.cohort(self.db, "fcarry"))
        self.screened(H, observe=False)
        self.assertTrue(self.status().startswith("forward test: cohort fcarry:fwd202612m12, M 2"))
        cf = families.cohort(self.db, "fcarry")
        a, b, b6 = ts(2026, 12, 1), ts(2027, 12, 1) - 1, ts(2027, 6, 1) - 1
        self.assertEqual((cf["cohort"], cf["members"], cf["survivors"], cf["selected"], cf["not_selected"]),
                         ("fcarry:fwd202612m12", sorted(BASE), sorted([F, L]), [L, F], []))
        self.assertEqual((cf["M"], cf["alpha_F"], cf["alpha_i"]), (2, 0.0125, 0.00625))
        self.assertEqual((cf["window"], cf["sub_window"], cf["start"], cf["end"], cf["sub_end"]),
                         ("fwd202612m12", "fwd202612m06", a, b, b6))
        self.assertEqual((cf["interim_not_before"], cf["final_not_before"]), (b6 + 1 + LAG, b + 1 + LAG))
        self.assertEqual(self.ledger(), [("family:fcarry", 0.0125, "A8 reserve"), ("family:fcarry", -0.0125, "A8 spend"),
                                         (L, 0.00625, "A8 spend"), (F, 0.00625, "A8 spend")])
        self.assertAlmostEqual(families.alpha_reserved(self.db), 0.0125)      # spent, never released
        self.assertEqual(lifecycle.state(self.db, S), "SUPPRESSED")
        for e in (L, F):
            j = jobs.get(self.db, f"observe_interim|{e}")
            self.assertEqual((j["kind"], j["next_run"], j["payload"]), ("observe_interim", ts(2027, 6, 1) + LAG,
                                                                        {"start": a, "months": 6,
                                                                         "cohort": cf["cohort"]}))
            self.assertIsNone(jobs.get(self.db, f"observe|{e}"))
        self.assertEqual(sorted((p["window"], p["cohort"]) for p in self.events("observation.started")),
                         [("fwd202612m12", cf["cohort"])] * 2)
        self.assertEqual(self.db.one("SELECT COUNT(*) FROM events WHERE kind LIKE 'forward.%'")[0], 0)
        self.now[0] = ts(2027, 1, 15)                                          # M and alpha_i are never recomputed
        for _ in range(2):
            fleet.strategy_pass(self.db)
        self.assertEqual((len(self.events("cohort.fixed")), len(self.ledger()), self.events("family.closed")),
                         (1, 4, []))

    def test_the_window_starts_the_month_after_the_close_and_never_before_december_2026(self):
        for now, start in ((ts(2026, 10, 20), ts(2026, 12, 1)), (ts(2026, 11, 30, 23, 59, 59), ts(2026, 12, 1)),
                           (ts(2026, 12, 1), ts(2027, 1, 1)), (ts(2027, 12, 31, 12), ts(2028, 1, 1))):
            with self.subTest(now=now):
                self.assertEqual(families.window_start(FCARRY, now), start)
        self.register()
        for e in BASE:
            self.screened(e, observe=e == F)
        self.now[0] = ts(2026, 12, 15)
        fleet.strategy_pass(self.db)
        cf = families.cohort(self.db, "fcarry")
        self.assertEqual((cf["window"], cf["sub_window"], cf["start"]), ("fwd202701m12", "fwd202701m06", ts(2027, 1, 1)))

    def test_at_most_three_by_validation_net_sharpe_and_the_rest_not_selected(self):
        fam = copy.deepcopy(FCARRY)
        fam["instances"][0]["successor"]["trigger"]["all"] = ["rejected_early == false"]
        real = families.load
        with mock.patch.object(families, "load", lambda p: copy.deepcopy(fam) if p == "fcarry" else real(p)):
            self.register()
            self.screened(F, sharpe=1.0)
            self.assertEqual(fleet.strategy_pass(self.db)["registered"], [S])   # the parent passed: triggered
            for e, sharpe in ((L, 3.0), (H, 2.0), (S, 0.5)):
                self.screened(e, sharpe=sharpe)
            fleet.strategy_pass(self.db)
        cf = families.cohort(self.db, "fcarry")
        self.assertEqual((cf["selected"], cf["not_selected"], cf["M"]), ([L, H, F], [S], 3))
        self.assertAlmostEqual(cf["alpha_i"], 0.0125 / 3)
        res = self.db.one("SELECT label, verdict FROM results WHERE exp_id=? ORDER BY id DESC LIMIT 1", S)
        self.assertEqual(res["label"], "EXPLORATORY")
        self.assertTrue(res["verdict"].startswith(families.NOT_SELECTED), res["verdict"])
        self.assertEqual(lifecycle.state(self.db, S), "REJECTED")
        self.assertIsNone(jobs.get(self.db, f"observe_interim|{S}"))
        self.assertEqual([x[0] for x in self.ledger()[2:]], [L, H, F])
        self.assertAlmostEqual(families.alpha_reserved(self.db), 0.0125)

    def test_m_zero_releases_alpha_and_closes_the_family_futile(self):
        self.register()
        for e in BASE:
            self.screened(e, observe=False)
        self.assertEqual(self.status(), "closed: FUTILE_IN_SAMPLE")
        cf = families.cohort(self.db, "fcarry")
        self.assertEqual((cf["M"], cf["alpha_i"], cf["window"], cf["cohort"]), (0, None, None, "fcarry:M0"))
        self.assertEqual(self.ledger(), [("family:fcarry", 0.0125, "A8 reserve"), ("family:fcarry", -0.0125, "A8 release")])
        self.assertAlmostEqual(families.alpha_reserved(self.db), 0.0)
        self.assertEqual(self.events("family.closed"), [{"family": "fcarry", "outcome": "FUTILE_IN_SAMPLE",
                                                         "cohort": "fcarry:M0", "alpha_released": 0.0125}])
        self.assertEqual(families.open_families(self.db), set())             # its slot is free again
        self.assertEqual(lifecycle.state(self.db, S), "SUPPRESSED")
        self.assertEqual(self.db.q("SELECT job_id FROM jobs WHERE kind LIKE 'observe%'"), [])
        self.assertEqual(self.events("observation.started"), [])
        for _ in range(2):
            self.assertEqual(self.status(), "closed: FUTILE_IN_SAMPLE")
        self.assertEqual((len(self.events("cohort.fixed")), len(self.ledger())), (1, 2))
        # test 27: with two more families closed without a forward PASS the programme stops
        for fid in ("faaa", "fbbb"):
            self.db.event("family.closed", "system:fixture", None, {"family": fid, "outcome": "UNTESTABLE"})
        with self.assertRaises(families.FamilyError) as c:
            families.request(self.db, "fcarry", "human:anton", "Anton approves F1 after reading it")
        self.assertIn("3 families in a row closed without a forward PASS", str(c.exception))

    def test_m_zero_for_data_reasons_is_untestable(self):
        self.register()
        for e in BASE:
            self.screened(e, data_ok=False)
        self.assertEqual(self.status(), "closed: UNTESTABLE")
        self.assertEqual(self.ledger()[-1], ("family:fcarry", -0.0125, "A8 release"))

    def test_a_permanent_job_failure_stops_the_family_without_closing_its_cohort(self):
        self.register()
        self.screened(F)
        self.screened(L)
        jobs.enqueue(self.db, f"diagnose|{F}", "diagnose", F, {})
        with self.db.tx():
            self.db.con.execute("UPDATE jobs SET status='failed' WHERE job_id IN (?, ?)", (f"diagnose|{F}",
                                                                                        f"cost|{H}"))
        self.assertEqual(families.failed_jobs(self.db, BASE), [f"cost|{H}"])  # diagnostics never count
        for _ in range(3):
            self.assertEqual(self.status(), "stopped: 1 job(s) failed permanently")
        w = [p for p in self.events("family.waiting") if p.get("topic") == "cohort"]
        self.assertEqual(len(w), 1)
        self.assertIn(f"job cost|{H} failed permanently", w[0]["reasons"][0])
        self.assertIsNone(families.cohort(self.db, "fcarry"))
        self.assertEqual(self.events("family.closed"), [])
        self.assertAlmostEqual(families.alpha_reserved(self.db), 0.0125)


class CodePin(A5Base):
    """Test 26: changing the family file or the module after registration makes every later step fail closed."""

    def test_a_changed_family_file_or_module_fails_the_next_step_and_the_cohort(self):
        self.register()
        for k in ("family", "module"):
            with self.subTest(k):
                old = self.blobs[k]["working"]
                self.blobs[k]["working"] = "edited-after-registration"
                with self.assertRaises(pipeline.StepError) as c:
                    pipeline.step_data(self.db, {"exp_id": F}, "data-1")
                self.assertIn("amendment 8 point 18", str(c.exception))
                self.assertEqual(lifecycle.state(self.db, F), "REGISTERED")    # nothing moved
                self.blobs[k]["working"] = old
        for e in BASE:
            self.screened(e)
        self.blobs["module"]["working"] = "edited-after-registration"
        self.assertTrue(self.status().startswith("stopped:"))
        self.assertIsNone(families.cohort(self.db, "fcarry"))
        self.assertIn("point 18", self.events("family.waiting")[-1]["reasons"][0])
        self.blobs["module"]["working"] = self.blobs["module"]["committed"]
        self.assertTrue(self.status().startswith("forward test"))

    def test_the_fleet_fails_the_job_instead_of_running_edited_code(self):
        self.register()
        self.blobs["family"]["working"] = "edited-after-registration"
        agent = [a for a in fleet.agents(self.db_path) if a.name == "data-1"][0]
        agent(self.db)
        dead = self.db.q("SELECT job_id, error FROM jobs WHERE status='failed'")
        self.assertEqual(len(dead), 1)
        self.assertIn("point 18", dead[0]["error"])
        self.assertEqual(self.db.one("SELECT COUNT(*) FROM transitions WHERE to_state='SCREENING'")[0], 0)
        self.assertEqual(self.status(), "stopped: 1 job(s) failed permanently")


FWD_SPAN = (ts(2026, 12, 1), ts(2027, 12, 1))


class ForwardBase(A5Base):
    """A synthetic, unseen 2026-12..2027-11 market of six coins (min_symbols 4 here) for the forward tests. data._fetch
    raises for any file that is not on disk or a remembered 404 (the fixture's stand-in for the archive's answer)."""
    market = None

    @classmethod
    def setUpClass(cls):
        cls.market = tempfile.mkdtemp(prefix="labfamA5m")
        write_pairs(cls.market, SIX, span=FWD_SPAN)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.market, ignore_errors=True)

    def setUp(self):
        super().setUp()
        self.fwd = os.path.join(self.tmp, "fwdmarket")
        shutil.copytree(self.market, self.fwd)
        real = families.load

        def small(path_or_fid):
            fam = real(path_or_fid)
            fam["universe"]["min_symbols"] = 4
            return fam

        def disk_or_404(url, path, get=None):
            if os.path.exists(path):
                return path
            if url in families.absent():
                return None                                                    # a remembered 404: no request
            raise AssertionError(f"a family test tried to fetch {url}")
        self.saved = dict(data.SPLITS), dict(data.GATEWAY_SPLIT)
        self.p5 = [mock.patch.object(data, "CACHE", self.fwd), mock.patch.object(data, "UNIVERSE_30_V3", SIX),
                   mock.patch.object(data, "_fetch", disk_or_404), mock.patch.object(families, "load", small)]
        for p in self.p5:
            p.start()
        self.now[0] = ts(2026, 11, 29)                                         # after the embargo

    def tearDown(self):
        for p in reversed(self.p5):
            p.stop()
        data.SPLITS.clear(), data.SPLITS.update(self.saved[0])
        data.GATEWAY_SPLIT.clear(), data.GATEWAY_SPLIT.update(self.saved[1])
        super().tearDown()

    def cohort_of_one(self):
        """filt survives the screen with the frozen variant grid[0]; floor and hyst are rejected: M = 1."""
        self.ready(files=False)
        self.assertEqual(sorted(fleet.strategy_pass(self.db)["registered"]), BASE)
        self.screened(F, params=GRIDS["carry_filter"][0])
        for e in (L, H):
            self.screened(e, observe=False)
        fleet.strategy_pass(self.db)
        cf = families.cohort(self.db, "fcarry")
        self.assertEqual((cf["selected"], cf["M"], cf["alpha_i"], cf["window"]), ([F], 1, 0.0125, "fwd202612m12"))
        return cf

    def interim(self):
        return pipeline.step_observe_interim(self.db, {"exp_id": F}, "validation-1")

    def final(self):
        return pipeline.step_observe(self.db, jobs.get(self.db, f"observe|{F}"), "validation-1")

    def reads(self):
        return len(self.events("data.accessed"))


def never(b, f, p, fit=None, volume_by=None, extra=None):
    """A mechanism function that never holds anything: the interim look's futility."""
    return {s: [0.0] * len(x) for s, x in b.items()}


def always(b, f, p, fit=None, volume_by=None, extra=None):
    """A mechanism function that always holds every coin."""
    return {s: [1.0] * len(x) for s, x in b.items()}


class ForwardTest(ForwardBase):
    """Tests 20-22: the interim look reads months 1-6 only after they ended plus 7 days and can only reject; the final
    test decides with PSR_cons >= 1 - alpha_i from cohort.fixed."""

    def test_the_interim_look_waits_for_its_window_and_then_queues_the_final_test(self):
        cf = self.cohort_of_one()
        self.assertEqual(jobs.get(self.db, f"observe_interim|{F}")["next_run"], ts(2027, 6, 1) + LAG)
        self.now[0] = cf["interim_not_before"] - 1
        with self.assertRaises(data.ReservedData):
            self.interim()
        self.assertIsNone(self.db.one("SELECT 1 FROM datasets WHERE exp_id=?", F))     # nothing was read
        self.now[0] = cf["interim_not_before"]
        out = self.interim()
        self.assertEqual((out["state"], lifecycle.state(self.db, F)), ("OBSERVATION", "OBSERVATION"), out)
        fin = jobs.get(self.db, f"observe|{F}")
        self.assertEqual((fin["kind"], fin["next_run"], fin["payload"]),
                         ("observe", cf["final_not_before"], {"start": cf["start"], "months": 12,
                                                              "cohort": cf["cohort"]}))
        self.assertIsNone(self.db.one("SELECT 1 FROM results WHERE exp_id=? AND label='VALIDATION'", F))
        self.assertEqual([tuple(r) for r in self.db.q("SELECT DISTINCT split, window_start, window_end FROM datasets "
                                                      "WHERE exp_id=?", F)], [("forward", cf["start"], cf["sub_end"])])
        paths = [r[0] for r in self.db.q("SELECT path FROM datasets WHERE exp_id=?", F)]
        self.assertEqual(sum("/spot_klines/" in p for p in paths), 6 * 6)       # months 1-6 only, spot included
        self.assertEqual(self.events("family.interim")[0]["outcome"], "continue")
        n = self.reads()                  # the look runs once: a retry completes it (engineering finding #3; this test
        self.assertEqual(self.interim()["verdict"], pipeline.INTERIM_CONTINUE)     # pinned a StepError before)
        self.assertEqual((self.reads(), len(self.events("family.interim"))), (n, 1))

    def test_the_validation_agent_runs_the_interim_look(self):
        cf = self.cohort_of_one()
        self.now[0] = cf["interim_not_before"]
        with self.db.tx():                                                      # the queue's clock is the real one
            self.db.con.execute("UPDATE jobs SET next_run=0 WHERE job_id=?", (f"observe_interim|{F}",))
        agent = [a for a in fleet.agents(self.db_path) if a.name == "validation-1"][0]
        agent(self.db)
        self.assertEqual(jobs.get(self.db, f"observe_interim|{F}")["status"], "done")
        art = pipeline.frozen_artifact(self.db, F, "observe_interim")          # hash-recorded like every step
        self.assertEqual((art["window"], art["decisional"]), ("fwd202612m06", "reject-only"))
        self.assertEqual(jobs.get(self.db, f"observe|{F}")["status"], "queued")

    def test_futility_rejects_and_queues_no_final_test(self):
        cf = self.cohort_of_one()
        self.now[0] = cf["interim_not_before"]
        flat = lambda b, f, p, fit=None, volume_by=None, extra=None: {s: [0.0] * len(x) for s, x in b.items()}  # noqa
        with mock.patch.object(fcarry, "carry_filter", flat):
            out = self.interim()
        self.assertEqual((out["state"], lifecycle.state(self.db, F)), ("REJECTED", "REJECTED"))
        res = self.db.one("SELECT verdict FROM results WHERE exp_id=? AND label='VALIDATION'", F)
        self.assertTrue(res["verdict"].startswith(families.FUTILITY), res["verdict"])
        self.assertIsNone(jobs.get(self.db, f"observe|{F}"))
        self.assertEqual(self.status(), "closed: FAIL")
        self.assertEqual(self.ledger()[-1], (F, 0.0125, "A8 spend"))            # a FAIL gives no alpha back

    def test_the_final_test_decides_with_alpha_i_from_the_cohort(self):
        cf = self.cohort_of_one()
        accounts = copy.deepcopy(paper.FORWARD_ACCOUNTS)
        self.now[0] = cf["final_not_before"]
        with self.assertRaises(pipeline.StepError):                             # never before the interim look
            pipeline.step_observe(self.db, {"exp_id": F, "payload": {"start": cf["start"], "months": 12}},
                                  "validation-1")
        self.now[0] = cf["interim_not_before"]
        self.interim()
        self.now[0] = cf["final_not_before"] - 1
        with self.assertRaises(data.ReservedData):
            self.final()
        self.now[0] = cf["final_not_before"]
        out = self.final()
        res = self.db.one("SELECT verdict, metrics FROM results WHERE exp_id=? AND label='VALIDATION'", F)
        m = json.loads(res["metrics"])
        self.assertEqual((m["alpha_i"], m["M"], m["cohort"], m["window"]), (0.0125, 1, cf["cohort"], "fwd202612m12"))
        self.assertIn("forward luck check PSR_cons >= 0.9875", m["gates"])
        self.assertLessEqual(m["psr_cons"], m["psr"]["iid"])
        self.assertLessEqual(m["psr"]["n_eff"], m["psr"]["n"])
        self.assertTrue({"mechanism attribution: funding income - costs > 0",
                         "mechanism attribution: gross ratio P&L <= funding income"} <= set(m["gates"]))
        self.assertEqual((out["state"], lifecycle.state(self.db, F)), ("SCREEN_PASSED", "SCREEN_PASSED"), res["verdict"])
        self.assertTrue(res["verdict"].startswith(families.FORWARD_PASS), res["verdict"])
        perp, raw = {}, {}                                                       # the benchmark: the perps
        for s in SIX:
            perp[s], raw[s], _ = data.load(data.files_for(s, cf["window"]), cf["window"])
        want = json.loads(json.dumps(pipeline._strip(pipeline._benchmark(perp, raw, catalogue.COSTS)), default=str))
        self.assertEqual(m["benchmark"], want)
        self.assertEqual(self.status(), "closed: PASS")
        self.assertIn(F, families.forward_passes(self.db))
        registry.record_result(self.db, F, "VALIDATION", "FAIL (holdout): fixture", {}, {}, "system:fixture")
        self.assertEqual(families.forward_outcome(self.db, F), "PASS")          # a later holdout never rewrites it
        # test 20: amendment 7's forward family is untouched and families write no forward.* event
        self.assertEqual(paper.FORWARD_ACCOUNTS, accounts)
        self.assertEqual(set(paper.FORWARD_ACCOUNTS), FWD_IDS)
        self.assertEqual(self.db.one("SELECT COUNT(*) FROM events WHERE kind LIKE 'forward.%'")[0], 0)
        # point 16: a family forward PASS never takes the automatic promotion path
        promotion.set_policy(self.db, True, "human:anton", "automatic promotion on in this test")
        with mock.patch.object(promotion, "supervisor_ok", lambda db, now=None: True):
            d = promotion.decide(self.db, F)
        self.assertFalse(d["allowed"])
        self.assertEqual(lifecycle.state(self.db, F), "SCREEN_PASSED")
        self.assertIsNone(self.db.one("SELECT 1 FROM events WHERE kind='holdout.opened'"))

    def test_unlisted_coins_are_excluded_and_a_delisted_coin_only_from_the_day_after(self):
        """Point 11 with amendment 7 point 5. This test pinned LINK in 'excluded' (dropped from the whole window), the
        survivorship of finding protocol-statistics #8; LINK now counts until its last listed day."""
        cf = self.cohort_of_one()
        url, path = data.expected_paths("ADAUSDT", cf["window"], spot=True)["spot"][0]
        os.remove(path)                                                          # no spot file in month 1
        families._mark_absent(url)
        for kind, pairs in data.expected_paths("LINKUSDT", cf["window"], spot=True).items():
            for u, p in pairs[4:]:                                               # delisted from 2027-04
                os.remove(p)
                families._mark_absent(u)
        self.now[0] = cf["interim_not_before"]
        self.interim()
        self.now[0] = cf["final_not_before"]
        self.final()
        gone = {"LINKUSDT": {"last_listed_hour": ts(2027, 3, 31, 23), "excluded_from": "2027-04-01"}}
        for name in ("observe_interim", "observe"):
            art = pipeline.load_artifact(F, name)
            self.assertEqual((art["unlisted"], art["excluded"], art["delisted"]), (["ADAUSDT"], [], gone), name)
            self.assertEqual(art["symbols"], sorted(set(SIX) - {"ADAUSDT"}))
            self.assertNotIn("ADAUSDT", art["quality"])
            self.assertEqual((art["quality"]["LINKUSDT"]["listed_until"], art["quality"]["LINKUSDT"]["ok"]),
                             (ts(2027, 3, 31, 23), True))
        self.assertTrue(art["gates"]["forward data quality"])                    # 4 whole-window coins, min_symbols 4

    def test_running_forward_tests_continue_after_a_programme_stop_and_fail_closed_on_edited_code(self):
        cf = self.cohort_of_one()
        for fid in ("faaa", "fbbb", "fccc"):
            self.db.event("family.closed", "system:fixture", None, {"family": fid, "outcome": "FUTILE_IN_SAMPLE"})
        self.assertTrue(families.programme_stop(self.db))
        self.now[0] = cf["interim_not_before"]
        self.blobs["module"]["working"] = "edited-after-registration"
        with self.assertRaises(pipeline.StepError):
            self.interim()
        self.assertIsNone(self.db.one("SELECT 1 FROM datasets WHERE exp_id=?", F))
        self.blobs["module"]["working"] = self.blobs["module"]["committed"]
        self.assertEqual(self.interim()["state"], "OBSERVATION")


class PsrCons(unittest.TestCase):
    """Test 22, the luck check: PSR_cons is never above today's PSR, n_eff never above n, and under a daily AR(1) null
    with rho = 0.3 it passes far less often than the iid PSR (amendment 8 point 20: about 0.017 against 0.048)."""

    @staticmethod
    def ar1(rng, rho, n, mu=0.0):
        x, prev = [], 0.0
        for _ in range(n):
            prev = rho * prev + rng.gauss(mu, 0.01)
            x.append(prev)
        return x

    def test_never_above_the_iid_psr_and_n_eff_never_above_n(self):
        rng = random.Random(1)
        for rho in (-0.5, 0.0, 0.3, 0.8):
            for _ in range(25):
                p, d = families.psr_cons(self.ar1(rng, rho, 200, mu=0.002))
                self.assertLessEqual(p, d["iid"])
                self.assertLessEqual(d["n_eff"], d["n"])
                if rho < 0:
                    self.assertEqual(d["n_eff"], d["n"])
        self.assertIsNone(families.psr_cons([0.01, 0.01, 0.01])[0])
        self.assertIsNone(families.psr_cons([0.01, -0.01])[0])

    def test_an_autocorrelated_null_passes_less_often(self):
        rng, need, n = random.Random(7), 1 - 0.0125, 1500
        iid = cons = 0
        for _ in range(n):
            p, d = families.psr_cons(self.ar1(rng, 0.3, 365))
            iid += d["iid"] >= need
            cons += (p or 0) >= need
        self.assertLess(cons, iid)
        self.assertLess(cons / n, 0.03)
        self.assertGreater(iid / n, 0.0125)                                      # the iid PSR is too lenient here


class MvrvSafety(unittest.TestCase):
    """Test 19: amendment 8 cohort events never count in amendment 2's cohort. With MVRV's fwd202611 event plus family
    observation events (one even naming the same window), MVRV's forward test still needs PSR >= 0.95 (N = 1)."""
    market = None

    @classmethod
    def setUpClass(cls):
        cls.saved = dict(data.SPLITS), dict(data.GATEWAY_SPLIT)
        cls.split = data.forward_split(data.FORWARD_MIN)
        a, b = data.window_bounds(cls.split)
        cls.market = tempfile.mkdtemp(prefix="labmvrv")
        write_pairs(cls.market, data.UNIVERSE_CM16, span=(a, b + 1))
        rng = random.Random(11)
        days = {s: {str(d): 0.5 + 2 * rng.random() for d in range(a, b, DAY)} for s in data.UNIVERSE_CM16}
        os.makedirs(os.path.join(cls.market, "coinmetrics"))
        with open(os.path.join(cls.market, "coinmetrics", f"CapMVRVCur-{cls.split}.json"), "w") as f:
            json.dump({"days": days}, f)

    @classmethod
    def tearDownClass(cls):
        data.SPLITS.clear(), data.SPLITS.update(cls.saved[0])
        data.GATEWAY_SPLIT.clear(), data.GATEWAY_SPLIT.update(cls.saved[1])
        shutil.rmtree(cls.market, ignore_errors=True)

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="labmvrve")
        self.db = DB(os.path.join(self.tmp, "lab.db"))
        a, b = data.window_bounds(self.split)

        def no_fetch(url, path, get=None):
            if os.path.exists(path):
                return path
            raise AssertionError(f"a test tried to fetch {url}")
        self.p = [mock.patch.object(data, "CACHE", self.market), mock.patch.object(data, "_fetch", no_fetch),
                  mock.patch.object(data, "CLOCK", lambda: b + LAG + 1),
                  mock.patch.object(pipeline, "ARTIFACTS", os.path.join(self.tmp, "artifacts")),
                  mock.patch.object(pipeline, "REPORTS", os.path.join(self.tmp, "reports")),
                  mock.patch.object(registry, "last_commit", lambda p: "c0ffee"),
                  mock.patch.object(registry, "blob_at", lambda c, p: "blob-test")]
        for p in self.p:
            p.start()

    def tearDown(self):
        for p in reversed(self.p):
            p.stop()
        self.db.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_mvrv_still_needs_0_95(self):
        eid, (a, b) = "E_mvrv_value_p3", data.window_bounds(self.split)
        self.db.append("experiments", exp_id=eid, version=2, created_ts=0, mechanism_tag="onchain_value_mvrv",
                       fingerprint="f", spec_json=pipeline.template_spec("mvrv_value"))
        self.db.append("transitions", exp_id=eid, ts=0, from_state=None, to_state="OBSERVATION", actor="fixture",
                       reason="fixture: entered observation")
        before = a - DAY
        for e, p in ((eid, {"window": self.split, "start": a, "end": b}),
                     (F, {"window": self.split, "start": a, "end": b, "cohort": "ffix:fwd202611", "family": "ffix"}),
                     (L, {"window": self.split, "start": a, "end": b, "cohort": "ffix:fwd202611", "family": "ffix"}),
                     (H, {"window": "fwd202612m12", "start": ts(2026, 12, 1), "end": ts(2027, 12, 1) - 1,
                          "cohort": "fcarry:fwd202612m12", "family": "fcarry"})):
            self.db.append("events", ts=before, kind="observation.started", actor="system:fixture", exp_id=e,
                           payload=p)
        frozen(self.db, eid, "cost", {"selected": 0})
        frozen(self.db, eid, "backtest", {"variants": [{"variant": 0, "params": {"mode": "level", "k": 3}, "fit": None,
                                                        "positions": {}}]})
        out = pipeline.step_observe(self.db, {"exp_id": eid, "payload": {"start": a, "months": 6}}, "validation-1")
        res = json.loads(self.db.one("SELECT metrics FROM results WHERE exp_id=?", eid)["metrics"])
        self.assertEqual(res["cohort"], 1)
        self.assertIn("forward luck check PSR >= 0.9500", res["gates"])
        self.assertTrue(out["verdict"].startswith(("PASS (forward test)", "FAIL (forward test)")))
        self.assertEqual(data.forward_split(data.FORWARD_MIN, 6), "fwd202611")
        self.assertEqual(data.SPLITS["fwd202611"], ((2026, 11), (2027, 4)))


class RosterAndSafety(unittest.TestCase):
    """Test 28 adapted (no roster or timer change): the same agents and intervals, the validation agents also run the
    interim look, and no family code schedules itself or touches orders."""

    def test_roster_names_intervals_and_no_timers(self):
        self.assertEqual([(n, e) for n, _, _, _, e, _ in fleet.ROSTER],
                         [("data-1", None), ("discovery-scanner", 3600), ("premium-watch", 60),
                          ("discovery-catalogue", 600), ("strategy-1", 30), ("backtest-1", None),
                          ("backtest-2", None), ("cost-1", None), ("cost-2", None), ("adversarial-1", None),
                          ("adversarial-2", None), ("adversarial-3", None), ("validation-1", None),
                          ("validation-2", None), ("report-1", None), ("paper-1", 60), ("risk-1", 15)])
        kinds = {n: k for n, _, k, _, _, _ in fleet.ROSTER}
        for n in ("validation-1", "validation-2"):
            self.assertEqual(kinds[n], ("validate", "holdout", "observe", "observe_interim"))
        self.assertTrue({"observe", "observe_interim"} <= fleet.HEAVY)
        self.assertEqual(command.STAGE_OF_KIND["observe_interim"], "VALIDATION")
        self.assertIs(pipeline.HANDLERS["observe_interim"], pipeline.step_observe_interim)
        import inspect
        src = ""
        for p in glob.glob(os.path.join(families.MODULE_DIR, "*.py")):
            with open(p, encoding="utf-8") as f:
                src += f.read()
        src += "".join(inspect.getsource(f) for f in (pipeline._forward_market, pipeline.step_observe_interim,
                                                      pipeline._family_forward, pipeline._declare_holdout,
                                                      pipeline.step_holdout, command.families_card,
                                                      command._family_row))
        for word in ("Timer(", "import sched", "crontab", "systemctl", "schtasks", "sim_orders", "submit_taker",
                     "PaperEngine", "forward.approved"):
            self.assertNotIn(word, src)


class ProgrammeStop(A3Base):
    """Test 27: no new family approval after 2028-06-30 without a forward PASS (point 15 c)."""

    def test_approvals_are_refused_after_june_2028_without_a_forward_pass(self):
        families.discover_all(self.db)
        self.revive()                                                            # revival before approve-family
        self.now[0] = ts(2028, 7, 1)
        with self.assertRaises(families.FamilyError) as c:
            families.request(self.db, "fcarry", "human:anton", "Anton approves F1 after reading it")
        self.assertIn("no forward PASS by 2028-06-30", str(c.exception))
        self.now[0] = ts(2028, 6, 30, 12)
        self.assertTrue(families.request(self.db, "fcarry", "human:anton", "Anton approves F1 after reading it"))


# ---------- phase A6: the sealed holdout, the read model, and the rest of the design (C) list (tests 1, 6, 24) ----------
HOLDOUT_SPAN = (ts(2024, 1, 1), ts(2025, 1, 1))
NINE = SIX + data.HOLDOUT_SEEN
HOLDOUT_GATES = {"net_mean_daily > 0", "one-sided 95% lower bound > 0", "net Sharpe > buy-and-hold",
                 "holdout data quality (min symbols)"}
OPEN_REASON = "Anton opens the 2024 holdout after the family forward PASS"


class Holdout(A5Base):
    """Test 24: after a forward PASS the sealed 2024 holdout is reachable only by the human path typed in a terminal
    (never the automatic path or the dashboard); it opens once as one declared file set that holds the spot files, the
    family file blob is the gateway's code hash (a catalogue change never locks it), BTC/ETH/SOL are never read, 2024
    files come only through the embargo guard after 2026-11-27, and nothing raises a KeyError. The registered universe
    is six synthetic coins (min_symbols 5 here) plus BTC/ETH/SOL, which have no 2024 file: any read of them would
    fail."""
    market = None

    @classmethod
    def setUpClass(cls):
        cls.market = tempfile.mkdtemp(prefix="labfamA6m")
        write_pairs(cls.market, SIX, span=HOLDOUT_SPAN)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.market, ignore_errors=True)

    def setUp(self):
        super().setUp()
        self.hold, self.clean, self.fetched = os.path.join(self.tmp, "holdmarket"), True, []
        real = families.load

        def small(path_or_fid):
            fam = real(path_or_fid)
            fam["universe"]["min_symbols"] = 5
            fam["universe"]["clean_holdout"] = self.clean
            return fam

        def disk_only(url, path, get=None):
            self.fetched.append((url, getattr(get, "guarded", False)))
            if os.path.exists(path):
                return path
            raise AssertionError(f"a family test tried to fetch {url}")
        self.saved = dict(data.SPLITS), dict(data.GATEWAY_SPLIT)
        self.p6 = [mock.patch.object(data, "CACHE", self.hold), mock.patch.object(data, "UNIVERSE_30_V3", NINE),
                   mock.patch.object(data, "_fetch", disk_only), mock.patch.object(families, "load", small)]
        for p in self.p6:
            p.start()
        self.now[0] = ts(2026, 11, 29)

    def tearDown(self):
        for p in reversed(self.p6):
            p.stop()
        data.SPLITS.clear(), data.SPLITS.update(self.saved[0])
        data.GATEWAY_SPLIT.clear(), data.GATEWAY_SPLIT.update(self.saved[1])
        super().tearDown()

    def cli(self, *argv):
        lines = []
        rc = main(list(argv), self.db_path, lines.append)
        return rc, "\n".join(lines)

    def forward_pass(self, approve=True):
        """filt survives the screen (M = 1); a fixture forward PASS, recorded the way the forward step records it (the
        cohort id and its hash-matching observe.json; changed with finding protocol-statistics #2, which refuses a
        PASS without them), takes the automatic edge the forward test takes."""
        self.register()
        self.screened(F, params=GRIDS["carry_filter"][0])
        for e in (L, H):
            self.screened(e, observe=False)
        fleet.strategy_pass(self.db)
        cf = families.cohort(self.db, "fcarry")
        art = pipeline.save_artifact(F, "observe", {"window": cf["window"], "cohort": cf["cohort"], "fixture": True})
        rid = registry.record_result(self.db, F, "VALIDATION", families.FORWARD_PASS + ": fixture",
                                     {"cohort": cf["cohort"]}, {"artifacts": [art]}, "system:validation-1")
        ev = {"result_id": rid}
        lifecycle.auto_transition(self.db, F, "SCREEN_PASSED", "system:validation-1", "forward PASS in this test", ev,
                                  guards=(registry.make_result_guard(ev),))
        self.assertEqual(self.status(), "closed: PASS")
        if not approve:
            return None
        rc, text = self.cli("approve", F, "VALIDATION", "--reason", OPEN_REASON, "--committed",
                            "research/PROTOCOL_V3.md")
        self.assertEqual(rc, 0, text)
        return text.split(": ")[1].split()[0]

    def test_only_the_human_terminal_path_opens_one_declared_set_under_the_family_blob(self):
        snapshot = json.dumps({k: sorted(v) for k, v in catalogue.TEMPLATES.items()}, sort_keys=True)
        code = self.forward_pass()
        with self.assertRaises(pipeline.StepError):                             # not before the human step
            pipeline.step_holdout(self.db, {"exp_id": F}, "validation-1")
        self.assertEqual(pipeline.enqueue_holdouts(self.db), 0)
        promotion.set_policy(self.db, True, "human:anton", "automatic promotion on in this test")
        with mock.patch.object(promotion, "supervisor_ok", lambda db, now=None: True):
            self.assertFalse(promotion.decide(self.db, F)["allowed"])           # never the automatic path
        with self.assertRaises(lifecycle.LifecycleError):                        # the dashboard's guards
            lifecycle.request_approval(self.db, F, "VALIDATION", "human:anton@dashboard", OPEN_REASON,
                                       {"committed_files": ["research/PROTOCOL_V2.md"]},
                                       guards=(registry.complete_spec_guard, families.no_web_guard))
        card = next(w for w in command.approvals(self.db)["waiting"] if w["exp_id"] == F)
        self.assertIsNone(card["to"])                                            # no button for a family instance
        self.assertIn("Kun i terminalen", card["action"])

        def no_terminal():
            raise families.FamilyError("refused: an interactive terminal is required")
        with mock.patch.object(families, "GUARD", no_terminal):
            rc, text = self.cli("confirm", code)
        self.assertEqual((rc, lifecycle.state(self.db, F)), (1, "SCREEN_PASSED"), text)
        rc, text = self.cli("confirm", code)                                     # typed in a terminal
        self.assertEqual((rc, lifecycle.state(self.db, F)), (0, "VALIDATION"), text)
        self.assertEqual(pipeline.enqueue_holdouts(self.db), 1)
        j = jobs.get(self.db, f"holdout|{F}")
        self.assertEqual((j["kind"], j["max_attempts"], j["timeout_s"]), ("holdout", 2, 1800))  # the data step's lease
        # the embargo: before 2026-11-28 no 2024 file is fetched and the job waits instead of failing
        self.now[0] = ts(2026, 11, 27, 23, 59, 59)
        with self.assertRaises(pipeline.Deferred) as c:
            pipeline.step_holdout(self.db, {"exp_id": F}, "validation-1")
        self.assertEqual(c.exception.until, families.EMBARGO_UNTIL)
        self.assertEqual(self.fetched, [])
        self.assertIsNone(self.db.one("SELECT 1 FROM events WHERE kind='holdout.opened'"))
        self.assertIsNone(self.db.one("SELECT 1 FROM datasets WHERE split='holdout'"))
        w = self.events("family.waiting")[-1]
        self.assertEqual((w["topic"], w["reasons"]), ("holdout", [families.embargo_reason("holdout")]))
        self.assertTrue(w["reasons"][0].startswith("holdout files are missing"), w["reasons"])
        # 2026-11-29 with the 2024 files cached: opened under catalogue blob A, read and decided under catalogue blob B
        self.now[0] = ts(2026, 11, 29)
        shutil.copytree(self.market, self.hold, dirs_exist_ok=True)
        pipeline._declare_holdout(self.db, F, pipeline._spec(self.db, F), "validation-1")
        with mock.patch.object(registry, "blob_at", lambda c, p: "another-catalogue-blob"), \
                mock.patch.object(templates, "catalogue_blob", lambda: "another-catalogue-blob"):
            self.assertEqual(pipeline._code_hash(), "another-catalogue-blob")   # a catalogue holdout would be locked
            out = pipeline.step_holdout(self.db, {"exp_id": F}, "validation-1")
        self.assertTrue(self.fetched and all(g for _, g in self.fetched))        # every file through the guard
        self.assertFalse([u for u, _ in self.fetched if any(s in u for s in data.HOLDOUT_SEEN)])
        opened = self.events("holdout.opened")
        self.assertEqual(len(opened), 1)
        self.assertEqual(opened[0]["code_hash"], CLEAN["family"]["committed"])
        paths = opened[0]["paths"]
        self.assertEqual(len(paths), 6 * 12 * 3)
        self.assertEqual(sum("/spot_klines/" in p for p in paths), 6 * 12)
        self.assertFalse([p for p in paths if any(s in p for s in data.HOLDOUT_SEEN)])
        rows = self.db.q("SELECT path, code_hash FROM datasets WHERE exp_id=? AND split='holdout'", F)
        self.assertEqual({r["path"] for r in rows}, set(paths))
        self.assertEqual({r["code_hash"] for r in rows}, {CLEAN["family"]["committed"]})
        art = pipeline.load_artifact(F, "holdout")
        self.assertEqual(set(art["gates"]), HOLDOUT_GATES)                       # no gate added, none removed
        self.assertTrue(art["gates"]["holdout data quality (min symbols)"])      # six coins, min_symbols 5
        self.assertEqual(art["not_read"], sorted(data.HOLDOUT_SEEN))
        self.assertIn("funding_income", art["attribution_recorded"])
        perp, raw = {}, {}                                                       # the benchmark: the perps, 2024
        for s in SIX:
            perp[s], raw[s], _ = data.load(data.files_for(s, "holdout"), "holdout")
        want = json.loads(json.dumps(pipeline._strip(pipeline._benchmark(perp, raw, catalogue.COSTS)), default=str))
        self.assertEqual(art["benchmark"], want)
        res = self.db.one("SELECT verdict FROM results WHERE exp_id=? AND label='VALIDATION' ORDER BY id DESC LIMIT 1",
                          F)
        self.assertEqual(out["verdict"], res["verdict"])
        self.assertTrue(all(art["gates"].values()), art["gates"])                # the synthetic carry pays in 2024
        self.assertTrue(res["verdict"].startswith("PASS (holdout)"), res["verdict"])
        self.assertIn("needs a live spot feed", res["verdict"])                  # never 'paper-eligible' (point 16)
        self.assertEqual(lifecycle.state(self.db, F), "VALIDATED")
        card = next(w for w in command.approvals(self.db)["waiting"] if w["exp_id"] == F)
        self.assertEqual((card["to"], "live spot-feed" in card["action"]), (None, True))
        with mock.patch.object(promotion, "supervisor_ok", lambda db, now=None: True):
            self.assertFalse(promotion.decide(self.db, F)["allowed"])           # no automatic paper trading either
        self.assertEqual(lifecycle.state(self.db, F), "VALIDATED")
        self.assertEqual(families.forward_outcome(self.db, F), "PASS")           # the holdout never rewrites it
        self.assertEqual(json.dumps({k: sorted(v) for k, v in catalogue.TEMPLATES.items()}, sort_keys=True), snapshot)

    def test_a_retried_holdout_never_reads_the_sealed_holdout_twice(self):
        """Review of fdd898a (engineering #5a): a crash between the holdout result and its edge is completed by the
        retry from the recorded result; the holdout is not opened, read or recorded a second time."""
        code = self.forward_pass()
        rc, text = self.cli("confirm", code)
        self.assertEqual((rc, lifecycle.state(self.db, F)), (0, "VALIDATION"), text)
        self.now[0] = ts(2026, 11, 29)
        shutil.copytree(self.market, self.hold, dirs_exist_ok=True)
        real = lifecycle.auto_transition

        def crash(db, eid, to, *a, **k):
            if to in ("VALIDATED", "REJECTED"):
                raise RuntimeError("the worker died after the holdout result")
            return real(db, eid, to, *a, **k)
        with mock.patch.object(lifecycle, "auto_transition", crash):
            with self.assertRaises(RuntimeError):
                pipeline.step_holdout(self.db, {"exp_id": F}, "validation-1")
        n = (self.db.one("SELECT COUNT(*) FROM results WHERE exp_id=?", F)[0], len(self.events("holdout.opened")),
             len(self.fetched), self.db.one("SELECT COUNT(*) FROM datasets WHERE split='holdout'")[0])
        out = pipeline.step_holdout(self.db, {"exp_id": F}, "validation-1")
        self.assertTrue(out["resumed"])
        self.assertEqual(lifecycle.state(self.db, F), "VALIDATED")
        self.assertEqual((self.db.one("SELECT COUNT(*) FROM results WHERE exp_id=?", F)[0],
                          len(self.events("holdout.opened")), len(self.fetched),
                          self.db.one("SELECT COUNT(*) FROM datasets WHERE split='holdout'")[0]), n)
        self.assertEqual(pipeline.step_holdout(self.db, {"exp_id": F}, "validation-1")["state"], "VALIDATED")

    def test_without_a_clean_holdout_the_instance_stops_at_screen_passed(self):
        """Changed with finding end-to-end #3: `lab approve` runs the terminal guard too, so it issues no code for this
        step; a code issued past the guard is still refused by `lab confirm`."""
        self.clean = False
        self.forward_pass(approve=False)
        card = next(w for w in command.approvals(self.db)["waiting"] if w["exp_id"] == F)
        self.assertIsNone(card["to"])
        self.assertIn("Ingen ren slut-test", card["action"])
        n = self.db.one("SELECT COUNT(*) FROM approvals")[0]
        rc, text = self.cli("approve", F, "VALIDATION", "--reason", OPEN_REASON, "--committed",
                            "research/PROTOCOL_V3.md")
        self.assertEqual(rc, 1, text)
        self.assertIn("stops at SCREEN_PASSED", text)
        self.assertEqual(self.db.one("SELECT COUNT(*) FROM approvals")[0], n)          # no code was issued
        code = lifecycle.request_approval(self.db, F, "VALIDATION", "human:anton", OPEN_REASON,
                                          {"committed_files": ["research/PROTOCOL_V3.md"]})
        rc, text = self.cli("confirm", code)
        self.assertEqual(rc, 1, text)
        self.assertIn("stops at SCREEN_PASSED", text)
        self.assertEqual(lifecycle.state(self.db, F), "SCREEN_PASSED")
        self.db.append("transitions", exp_id=F, ts=0, from_state="SCREEN_PASSED", to_state="VALIDATION",
                       actor="fixture", reason="fixture: forced past the guard")
        with self.assertRaises(pipeline.StepError) as c:
            pipeline.step_holdout(self.db, {"exp_id": F}, "validation-1")
        self.assertIn("amendment 8 point 16", str(c.exception))
        self.assertEqual((self.fetched, self.events("holdout.opened")), ([], []))

    def test_a_catalogue_holdout_declares_exactly_as_before(self):
        """The catalogue path of _declare_holdout is unchanged: its own files_for per symbol, the whole universe (its
        BTC/ETH/SOL exclusion happens after the read, as before), the catalogue blob as code hash."""
        seen = []
        spec = pipeline.template_spec("vol_managed_long")
        with mock.patch.object(data, "files_for", lambda s, sp, get=None: seen.append((s, sp, get)) or
                               {"klines": [], "funding": []}), \
                mock.patch.object(pipeline, "Gateway") as gw, mock.patch.object(pipeline, "_download") as dl:
            pipeline._declare_holdout(self.db, "E_vol_managed_long_p1", spec, "validation-1")
        dl.assert_not_called()
        self.assertEqual(seen, [(s, "holdout", None) for s in catalogue.universe("vol_managed_long")])
        self.assertEqual(gw.return_value.access.call_args[0][6], "blob-test")
        self.assertEqual(pipeline._symbols(spec, "holdout"), catalogue.universe("vol_managed_long"))
        e = catalogue.exp_id("vol_managed_long")
        pipeline.discover_catalogue(self.db)
        self.db.append("transitions", exp_id=e, ts=0, from_state=None, to_state="VALIDATION", actor="fixture",
                       reason="fixture: a human opened the holdout")
        self.assertEqual(pipeline.enqueue_holdouts(self.db), 1)
        j = jobs.get(self.db, f"holdout|{e}")
        self.assertEqual((j["max_attempts"], j["timeout_s"], j["priority"]), (2, 900, 5))


class FamiliesCard(A5Base):
    """The read-only families block of /api/kpis: approval state, alpha reserved/spent/released, the cohort and its
    windows, the close and the waiting reason. It writes nothing, checks the approval binding with git at most once a
    minute, and there is still no approval endpoint."""

    def card(self, now=None):
        before = self.db.con.total_changes
        k = command.families_card(self.db, now or self.now[0])
        self.assertEqual(self.db.con.total_changes, before)                     # read-only
        return k, next(f for f in k["families"] if f["family"] == "fcarry")

    def test_the_card_follows_a_family_from_approval_to_its_cohort(self):
        k, f = self.card()
        self.assertEqual((f["approval"], f["registered"], f["cohort"], f["closed"], f["waiting"]),
                         ("not approved", False, None, None, None))
        self.assertEqual(f["alpha"], {"family": 0.0125, "reserved": 0.0, "spent": 0.0, "released": 0.0})
        self.assertEqual((k["W0"], k["alpha_used"], k["open"], k["programme_stop"]), (0.05, 0.0, [], []))
        self.assertIn("terminal only", k["approval"])
        families.discover_all(self.db)
        self.revive()                                                            # revival before approve-family
        self.approve()
        fleet.strategy_pass(self.db)                                             # no screening file yet: it waits
        k, f = self.card()
        self.assertEqual((f["approval"], f["alpha"]["reserved"], k["alpha_used"]), ("approved", 0.0125, 0.0125))
        self.assertTrue(f["waiting"]["current"])
        self.assertIn(families.EMBARGO_REASON, f["waiting"]["reasons"][0])
        self.touch()
        self.assertEqual(sorted(fleet.strategy_pass(self.db)["registered"]), BASE)
        k, f = self.card()
        self.assertFalse(f["waiting"]["current"])                                # a later step superseded it
        self.assertEqual((f["registered"], f["members"], k["open"]), (True, {"REGISTERED": 3, "DISCOVERED": 1},
                                                                       ["fcarry"]))
        self.screened(F, sharpe=1.5)
        self.screened(L, sharpe=2.5)
        self.screened(H, observe=False)
        fleet.strategy_pass(self.db)
        k, f = self.card()
        cf = families.cohort(self.db, "fcarry")
        self.assertEqual(f["cohort"]["cohort"], "fcarry:fwd202612m12")
        self.assertEqual({x: f["cohort"][x] for x in ("M", "alpha_i", "window", "sub_window", "interim_not_before",
                                                      "final_not_before", "selected")},
                         {x: cf[x] for x in ("M", "alpha_i", "window", "sub_window", "interim_not_before",
                                             "final_not_before", "selected")})
        self.assertEqual(f["alpha"], {"family": 0.0125, "reserved": 0.0, "spent": 0.0125, "released": 0.0})
        self.assertAlmostEqual(k["alpha_used"], 0.0125)
        self.assertEqual(f["members"], {"OBSERVATION": 2, "REJECTED": 1, "SUPPRESSED": 1})
        self.assertIn("families", command.kpis(self.db, 900, self.now[0]))     # the block is part of /api/kpis

    def test_m_zero_shows_the_release_and_the_close(self):
        self.register()
        for e in BASE:
            self.screened(e, observe=False)
        fleet.strategy_pass(self.db)
        k, f = self.card()
        self.assertEqual((f["closed"], f["cohort"]["M"], f["cohort"]["window"]), ("FUTILE_IN_SAMPLE", 0, None))
        self.assertEqual(f["alpha"], {"family": 0.0125, "reserved": 0.0, "spent": 0.0, "released": 0.0125})
        self.assertEqual((k["alpha_used"], k["open"]), (0.0, []))

    def test_the_binding_is_checked_at_most_once_a_minute_and_a_void_approval_shows(self):
        families.discover_all(self.db)
        self.revive()                                                            # revival before approve-family
        self.approve()
        calls = []
        real = families.approval
        with mock.patch.object(families, "approval", lambda db, fid: calls.append(fid) or real(db, fid)):
            t0 = self.now[0] + 1000
            for dt in (0, 10, 59):
                self.assertEqual(self.card(t0 + dt)[1]["approval"], "approved")
            self.assertEqual(len(calls), 1)
            self.blobs["module"]["committed"] = self.blobs["module"]["working"] = "changed"
            self.assertEqual(self.card(t0 + 59)[1]["approval"], "approved")    # cached for a minute
            self.assertTrue(self.card(t0 + 61)[1]["approval"].startswith("void"))
        families.revoke(self.db, "fcarry", "human:anton", "Anton withdraws F1 for now")
        self.assertEqual(self.card(t0 + 62)[1]["approval"], "revoked")
        self.assertEqual(self.card(t0 + 62)[1]["alpha"]["released"], 0.0125)

    def test_a_broken_family_file_never_breaks_the_kpis(self):
        with mock.patch.object(families, "load", mock.Mock(side_effect=ValueError("broken json"))):
            k = command.families_card(self.db, self.now[0])
        self.assertIn("broken json", k["families"][0]["error"])


class TemplateApprovals(A3Base):
    """Test 1, rest: the template approvals of mvrv_value, real_rate_filter and supply_dilution give the same result
    before and after a family approval and registration."""

    def test_the_three_template_approvals_are_unchanged_by_a_family(self):
        pipeline.discover_catalogue(self.db)
        three = ("mvrv_value", "real_rate_filter", "supply_dilution")
        for t in three:
            templates.confirm(self.db, templates.request(self.db, t, "human:anton", "fixture approval for tests"),
                              "human:anton")
        blob = templates.catalogue_blob()
        before = {t: templates.approval(self.db, t, blob) for t in catalogue.TEMPLATES}
        self.ready()
        self.assertEqual(sorted(pipeline.register_batch(self.db, BASE, "strategy-1")), BASE)
        self.assertEqual({t: templates.approval(self.db, t, blob) for t in catalogue.TEMPLATES}, before)
        self.assertTrue(all(before[t] is not None for t in three))
        self.assertEqual([t for t in catalogue.TEMPLATES if t not in three and before[t] is not None], [])


class Budget(A3Base):
    """Test 6, a property test: random sequences of request/confirm, revoke, registration, cohort (M = 0..3), close and
    screening rows never take the amendment 8 sum above W0 = 0.05; it always equals the model (alpha_F per approved,
    unreleased family); releases happen only for a revocation before registration or M = 0; a confirm is refused when
    the wealth left is below alpha_F; the 0.005 screening rows never count, and neither does a foreign row of any sign
    under a family-like id (finding protocol-statistics #3, PoC BudgetPrefix; drawn from a second generator, so the
    sequences are the ones this test ran before). Every fixture family here copies fcarry's tag, so the per-tag limits
    of point 3 (their own test, PerTagLimits) are switched off in this test only."""
    FOREIGN = (("family:{fid}", "version 2"), ("family:{fid}", "exploratory screening"), ("family:zzz", "version 2"),
               ("E_{fid}__m1_a8", "version 2"), ("FAMILY:{fid}", "A8 reserve"), ("E_screen_{fid}", "A8 spend"),
               ("E_{fid}__m1_a8", "A8 in-sample filter"))

    def setUp(self):
        super().setUp()
        real = families.load
        self.saved = dict(data.SPLITS), dict(data.GATEWAY_SPLIT)
        self.p7 = [mock.patch.object(families, "load", lambda p: dict(copy.deepcopy(FCARRY), family_id=p)
                                     if p.startswith("fp") else real(p)),
                   mock.patch.object(families, "module_path", lambda fid: os.path.join(families.MODULE_DIR,
                                                                                        "fcarry.py")),
                   mock.patch.object(families, "tag_problems", lambda db, fam, registration=False: [])]
        for p in self.p7:
            p.start()

    def tearDown(self):
        for p in reversed(self.p7):
            p.stop()
        data.SPLITS.clear(), data.SPLITS.update(self.saved[0])
        data.GATEWAY_SPLIT.clear(), data.GATEWAY_SPLIT.update(self.saved[1])
        super().tearDown()

    def member(self, fid, j, ev_id, survives):
        e = families.exp_id(fid, f"m{j}")
        self.db.append("experiments", exp_id=e, version=1, created_ts=0, mechanism_tag="fixture", fingerprint=e,
                       spec_json={"family": fid})
        self.db.append("transitions", exp_id=e, ts=0, from_state="DISCOVERED", to_state="REGISTERED",
                       actor="system:strategy-1", reason="fixture: registered",
                       evidence={"family_approval_event": ev_id})
        self.db.append("transitions", exp_id=e, ts=0, from_state="REGISTERED",
                       to_state="OBSERVATION" if survives else "REJECTED", actor="fixture", reason="fixture: screened")
        registry.record_result(self.db, e, "EXPLORATORY", (families.OBSERVE if survives else "REJECTED") + ": fixture",
                               {"validation": {"net_sharpe_ann": float(j)}}, {}, "system:fixture")
        return e

    def test_random_sequences_never_exceed_the_programme_wealth(self):
        seen = {"budget refusal": 0, "confirmed": 0, "revoke release": 0, "M0 release": 0, "spend": 0, "late revoke": 0}
        for seed in range(12):
            with self.subTest(seed=seed):
                self.db.close()
                self.db = DB(os.path.join(self.tmp, f"budget{seed}.db"))       # a fresh registry per sequence
                jobs.init(self.db)
                rng, n, model, pending = random.Random(seed), 0, {}, []
                frng = random.Random(1000 + seed)                               # foreign rows: their own draws
                for _ in range(40):
                    e, note = frng.choice(self.FOREIGN)
                    self.db.append("alpha_ledger", exp_id=e.format(fid=frng.choice(sorted(model) or ["fzzz"])), ts=0,
                                   alpha=-frng.choice((0.05, 0.0125, 0.005)), note=note)
                    op = rng.choice(("request", "request", "confirm", "confirm", "revoke", "register", "cohort",
                                     "close", "screening"))
                    used = sum(a for a in model.values())
                    if op == "request":
                        n += 1
                        fid = f"fp{seed:02d}{n:03d}"
                        discovered(self.db, fid, families.load(fid))          # revival before approve-family
                        try:
                            pending.append((fid, families.request(self.db, fid, "human:anton", "Anton approves it",
                                                                  now=self.now[0])))
                        except families.FamilyError as e:
                            self.assertTrue(used + 0.0125 > families.W0 + 1e-12 or families.programme_stop(self.db),
                                            str(e))
                    elif op == "confirm" and pending:
                        fid, code = pending.pop(rng.randrange(len(pending)))
                        short = used + 0.0125 > families.W0 + 1e-12
                        try:
                            families.confirm(self.db, code, "abcdef01", "human:anton", now=self.now[0])
                            self.assertFalse(short)
                            model[fid], seen["confirmed"] = 0.0125, seen["confirmed"] + 1
                        except families.FamilyError as e:
                            self.assertTrue(short or families.programme_stop(self.db), str(e))
                            if short:
                                self.assertIn("alpha budget", str(e))
                                seen["budget refusal"] += 1
                    elif op == "revoke" and model:
                        fid = rng.choice(sorted(model))
                        if families.registered(self.db, fid):
                            with self.assertRaises(families.FamilyError):
                                families.revoke(self.db, fid, "human:anton", "Anton withdraws it again")
                            seen["late revoke"] += 1
                        else:                                        # a second revocation releases nothing
                            self.assertAlmostEqual(families.revoke(self.db, fid, "human:anton",
                                                                   "Anton withdraws it again"), model[fid])
                            seen["revoke release"] += bool(model[fid])
                            model[fid] = 0.0
                    elif op == "register":
                        ok = [f for f in sorted(model) if model[f] and not families.registered(self.db, f)]
                        if ok:
                            fid = rng.choice(ok)
                            ev_id = families.approval(self.db, fid)
                            regs = [self.member(fid, j, ev_id, rng.random() < 0.6)
                                    for j in range(1, rng.randint(1, 4) + 1)]
                            self.db.event("batch.registered", "system:strategy-1", None,      # the base batch (point 7)
                                          {"batch": f"B-{fid}", "exp_ids": regs, "trial_cutoff_id": 0,
                                           "protocol_version": 3, "family": fid, "amendment": 8})
                    elif op == "cohort":
                        ok = [f for f in sorted(model) if families.registered(self.db, f) and
                              families.cohort(self.db, f) is None]
                        if ok:
                            fid = rng.choice(ok)
                            regs = families.registered_members(self.db, fid)
                            cf = families.fix_cohort(self.db, fid, families.load(fid), regs, "strategy-1", self.now[0])
                            surv = sum(lifecycle.state(self.db, e) == "OBSERVATION" for e in regs)
                            self.assertEqual(cf["M"], min(surv, 3))
                            if cf["M"]:
                                self.assertAlmostEqual(cf["alpha_i"] * cf["M"], 0.0125)
                                seen["spend"] += 1
                            else:
                                model[fid], seen["M0 release"] = 0.0, seen["M0 release"] + 1
                    elif op == "close":
                        ok = [f for f in sorted(model) if (families.cohort(self.db, f) or {}).get("M") and
                              families.closed(self.db, f) is None]
                        if ok:
                            self.db.event("family.closed", "system:strategy-1", None,
                                          {"family": rng.choice(ok), "outcome": rng.choice(("PASS", "FAIL"))})
                    elif op == "screening":
                        self.db.append("alpha_ledger", exp_id=f"E_screen_{n}", ts=0, alpha=0.005,
                                       note="exploratory screening")
                    got = families.alpha_reserved(self.db)
                    self.assertLessEqual(got, families.W0 + 1e-12)
                    self.assertAlmostEqual(got, sum(model.values()))
                for r in self.db.q("SELECT exp_id FROM alpha_ledger WHERE note=?", families.RELEASE_NOTE):
                    fid = r[0].split(":", 1)[1]
                    revoked = any(p.get("family") == fid for p in (json.loads(x[0]) for x in self.db.q(
                        "SELECT payload FROM events WHERE kind='family.revoked'")))
                    m0 = (families.cohort(self.db, fid) or {}).get("M") == 0
                    self.assertTrue(revoked != m0, fid)                      # exactly one allowed case per release
                    if revoked:
                        self.assertIsNone(families.cohort(self.db, fid))
        for k, v in seen.items():
            self.assertGreater(v, 0, (k, seen))                              # every path was exercised


# ---------- verifier findings of 2026-10-19, group 1: registration integrity (amendment 8 points 5-7 and 18) ----------
def cli(db_path, *argv):
    lines = []
    rc = main(list(argv), db_path, lines.append)
    return rc, "\n".join(lines)


def discover_cli(db_path, eid):
    return cli(db_path, "discover", eid, "--hypothesis", "h", "--mechanism", "harmless_tag", "--instrument", "i",
               "--horizon", "days", "--execution", "taker", "--source", "s")


def force_approval(db, fid="fcarry"):
    """A family.approved event and its reservation written past request/confirm (an approval from before a rule, or a
    forged one): what registration itself must still refuse."""
    eid = db.event("family.approved", "human:anton", None, {
        "family": fid, "blobs": families.bound_blobs(fid), "thresholds": families.thresholds(), "alpha_family": 0.0125,
        "instances": [i["id"] for i in FCARRY["instances"]], "approval_id": None,
        "reason": "fixture: written past request/confirm"})
    db.append("alpha_ledger", exp_id=f"family:{fid}", ts=0, alpha=0.0125, note="A8 reserve")
    return eid


def built(db, eid, **change):
    """The version 2 that _register_family_one builds for eid (the approval's blobs, the fixture's engine blobs)."""
    blobs = families.approval_payload(db, "fcarry")["blobs"]
    spec = families.instance_spec(FCARRY, families.instance_of(eid)[1], blobs, {f: "blob-test" for f in pipeline.ENGINE_CODE})
    spec.update(change)
    return spec


def add_row(db, eid, version, spec):
    """A spec version appended straight to the registry (past lab add-version)."""
    v = registry.latest(db, eid)
    db.append("experiments", exp_id=eid, version=version, created_ts=0, mechanism_tag=v["mechanism_tag"],
              fingerprint=v["fingerprint"], spec_json=spec, spec_path="research/families/fcarry.json",
              spec_commit="c0ffee", code_hash=CLEAN["family"]["committed"], note="fixture: written past add-version")


class ApprovedFamilyBindsWhatRegisters(A3Base):
    """Finding protocol-statistics #1 (PoCs ForgedSpec and DiscoverBypass; the ids of PoC BudgetPrefix): an approved
    family binds what registers. lab discover / lab add-version refuse family instance ids and ids with ':'; a family
    instance registers only with a version 1 the discovery agent wrote from the family file (its tag and fingerprint)
    and the version 2 built from the family file and the approval's blobs, equal field for field; no other version."""

    def test_lab_discover_and_add_version_refuse_family_ids(self):
        self.ready()
        path = os.path.join(self.tmp, "forged.json")
        with open(path, "w") as f:
            json.dump(built(self.db, F, costs=ZERO, min_symbols=1, holdout_exclude=[],
                            universe=["BTCUSDT", "ETHUSDT", "SOLUSDT"], code="research/families/fcarry.json",
                            alpha="0.0"), f)
        fam_blob, real = CLEAN["family"]["committed"], registry.blob_at
        with mock.patch.object(registry, "blob_at", lambda c, p: fam_blob if p.endswith(".json") else real(c, p)), \
                mock.patch.object(registry, "git_committed", lambda p: True):          # as git would answer
            rc, text = cli(self.db_path, "add-version", F, "--spec", path)
            self.assertEqual(rc, 1, text)
            self.assertIn("never added by hand", text)
            with self.assertRaises(registry.RegistryError):
                registry.add_version(self.db, F, path, "human:anton")
            for e in ("family:zzz", "x:y", "E_fcarry__zzz_a8", " E_fcarry__filt_a8", "E_FCARRY__FILT_A8", "E_x_a8"):
                with self.subTest(e):
                    rc, text = discover_cli(self.db_path, e)
                    self.assertEqual(rc, 1, text)
                    self.assertIn("reserved", text)
                    with self.assertRaises(registry.RegistryError):
                        registry.discover(self.db, e, "h", "harmless_tag", "i", "days", "taker", "s", "human:anton")
        self.assertEqual(registry.latest(self.db, F)["version"], 1)
        self.assertIsNone(self.db.one("SELECT 1 FROM experiments WHERE exp_id IN ('family:zzz', 'x:y', 'E_x_a8', "
                                      "'E_fcarry__zzz_a8', 'E_FCARRY__FILT_A8', ' E_fcarry__filt_a8')"))
        self.assertEqual(sorted(fleet.strategy_pass(self.db)["registered"]), BASE)    # the real path is unchanged
        spec = pipeline._spec(self.db, F)
        self.assertEqual(spec, json.loads(json.dumps(built(self.db, F))))
        self.assertEqual(spec["costs"]["taker_fee"], FCARRY["costs"]["taker_fee"])

    def test_a_version_2_that_is_not_the_build_or_any_version_3_never_registers(self):
        self.ready()
        add_row(self.db, H, 2, built(self.db, H, costs=ZERO, min_symbols=1, holdout_exclude=[]))   # PoC ForgedSpec
        self.assertEqual(fleet.strategy_pass(self.db)["registered"], [])
        self.assertEqual({lifecycle.state(self.db, e) for e in BASE}, {"DISCOVERED"})   # checked before any registers
        why = self.events("family.waiting")[-1]["reasons"]
        self.assertTrue(any(r.startswith(f"{H}: spec version 2 is not the one built") for r in why), why)
        with self.assertRaises(lifecycle.LifecycleError):
            families.register_transition(self.db, H, "fcarry", "system:strategy-1")
        add_row(self.db, L, 2, built(self.db, L))                 # the exact build an interrupted pass left is fine ...
        add_row(self.db, L, 3, built(self.db, L))                 # ... but no other version
        with self.assertRaises(lifecycle.LifecycleError):
            pipeline._register_family_one(self.db, L, registry.latest(self.db, L), "strategy-1")
        self.assertEqual(fleet.strategy_pass(self.db)["registered"], [])
        self.assertTrue(any(r.startswith(f"{L}: spec version 3 exists") for r in self.events("family.waiting")[-1][
            "reasons"]))
        self.assertEqual((self.family_batches(), families.registration_started(self.db, "fcarry")), ([], False))

    def test_instances_the_discovery_agent_did_not_write_are_neither_approved_nor_registered(self):
        self.assertEqual([discover_cli(self.db_path, e)[0] for e in BASE], [1, 1, 1])   # PoC DiscoverBypass: refused
        for e in BASE:                                                    # the same rows written past lab discover
            self.db.append("experiments", exp_id=e, version=1, created_ts=0, mechanism_tag="harmless_tag",
                           fingerprint=e, spec_json={"family": "fcarry", "instance": families.instance_of(e)[1],
                                                     "discovered_by": "human:anton"}, note="fixture")
            self.db.append("transitions", exp_id=e, ts=0, from_state=None, to_state="DISCOVERED", actor="human:anton",
                           reason="fixture: not the discovery agent")
        self.assertEqual([e for e, _, _ in families.discover_all(self.db)], [S])   # only the successor is new
        self.touch()
        with self.assertRaises(families.FamilyError) as c:
            self.approve()
        self.assertIn("not written by the discovery agent", str(c.exception))
        force_approval(self.db)
        self.assertEqual(fleet.strategy_pass(self.db)["registered"], [])
        why = self.events("family.waiting")[-1]["reasons"]
        self.assertTrue(any("not written by the discovery agent" in r for r in why), why)
        self.assertTrue(any("mechanism tag delta_neutral_funding_carry" in r for r in why), why)
        self.assertFalse(families.registration_started(self.db, "fcarry"))


class PartialBaseBatch(A3Base):
    """Finding 'approving before the revivals registers a partial base batch' (protocol-statistics #6, engineering #1,
    end-to-end #1; PoC PartialBatch): approve-family and confirm-family refuse until every base instance is revived
    (point 6), and the base batch registers only when every approved base instance is DISCOVERED, all together (point
    7); until then family.waiting names the others."""

    def test_approve_family_and_confirm_family_refuse_before_every_revival(self):
        import argparse
        from lab.__main__ import family_cmd
        families.discover_all(self.db)
        self.revive([F])
        with self.assertRaises(families.FamilyError) as c:
            self.approve()
        self.assertIn(f"{families.REVIVE_FIRST}: base instance(s) not DISCOVERED: {H} (SUPPRESSED), {L} (SUPPRESSED)",
                      str(c.exception))
        lines = []
        rc = family_cmd(argparse.Namespace(cmd="approve-family", fid="fcarry", reason="Anton approves F1 now"), self.db,
                        lines.append)
        self.assertEqual(rc, 1, lines)
        self.assertTrue(lines[-1].startswith(f"refused: {families.REVIVE_FIRST}"), lines)
        self.revive([L, H])
        code = families.request(self.db, "fcarry", "human:anton", "Anton approves F1 after reading it")
        lifecycle.auto_transition(self.db, H, "SUPPRESSED", "system:cli", "suppressed between request and confirm")
        with self.assertRaises(families.FamilyError) as c:
            families.confirm(self.db, code, "abcdef01", "human:anton")
        self.assertIn(families.REVIVE_FIRST, str(c.exception))
        self.assertIsNone(families.approval(self.db, "fcarry"))
        self.assertAlmostEqual(families.alpha_reserved(self.db), 0.0)

    def test_the_base_batch_registers_only_when_every_approved_instance_is_discovered(self):
        families.discover_all(self.db)
        self.revive([F])
        force_approval(self.db)                                    # approved while floor and hyst are still SUPPRESSED
        self.touch()
        for _ in range(2):
            self.assertEqual(fleet.strategy_pass(self.db)["registered"], [])        # PoC PartialBatch gave [F]
        self.assertEqual(lifecycle.state(self.db, F), "DISCOVERED")
        w = self.events("family.waiting")
        self.assertEqual(len(w), 1)
        self.assertIn(f"base instance(s) not DISCOVERED: {H} (SUPPRESSED), {L} (SUPPRESSED)", w[0]["reasons"][0])
        self.assertIn("revival comes before approve-family", w[0]["reasons"][0])
        self.assertTrue(fleet.strategy_pass(self.db)["families"]["fcarry"].startswith("waiting: base instance(s)"))
        with self.assertRaises(lifecycle.LifecycleError):          # no revival under the approval (review finding 1)
            self.revive([L])
        families.revoke(self.db, "fcarry", "human:anton", "revive floor and hyst first, then approve again")
        self.revive([L, H])
        self.approve()                                             # the path the waiting reason names
        self.assertEqual(sorted(fleet.strategy_pass(self.db)["registered"]), BASE)   # one batch with all three
        b = self.family_batches()
        self.assertEqual((len(b), b[0]["exp_ids"]), (1, BASE))
        self.assertTrue(families.registered(self.db, "fcarry"))


class BatchFailureResumes(A3Base):
    """Finding end-to-end #2: a failure inside the batch loop no longer strands the family. families.registered() is
    the family's base batch.registered event, so the next pass registers the remaining approved members, writes the
    batch once and queues the jobs of every member; a stop after the event queues the jobs that are missing."""

    def jobs_of(self, e):
        return sorted(r[0].split("|")[0] for r in self.db.q("SELECT job_id FROM jobs WHERE exp_id=?", e))

    def complete(self):
        b = self.family_batches()
        self.assertEqual((len(b), b[0]["exp_ids"]), (1, BASE))
        for e in BASE:
            self.assertEqual(lifecycle.state(self.db, e), "REGISTERED")
            self.assertEqual(self.jobs_of(e), sorted(pipeline.STEPS))
            self.assertEqual(sorted(jobs.get(self.db, f"validate|{e}")["depends_on"]),
                             sorted([f"adversarial|{e}"] + [f"cost|{m}" for m in BASE if m != e]))
        self.assertEqual(families.unfinished(self.db), [])
        self.assertEqual(fleet.strategy_pass(self.db)["registered"], [])
        self.assertEqual(len(self.family_batches()), 1)

    def test_a_failure_on_the_second_registration_is_completed_by_the_next_pass(self):
        self.ready()
        real, calls = families.register_transition, []

        def flaky(db, eid, fid, actor):
            calls.append(eid)
            if len(calls) == 2:
                raise sqlite3.OperationalError("database is locked")
            return real(db, eid, fid, actor)
        with mock.patch.object(families, "register_transition", flaky):
            self.assertEqual(fleet.strategy_pass(self.db)["registered"], [])
        self.assertEqual(calls, [F, L])
        self.assertEqual([lifecycle.state(self.db, e) for e in BASE], ["REGISTERED", "DISCOVERED", "DISCOVERED"])
        self.assertEqual(registry.latest(self.db, L)["version"], 1)              # rolled back with its transition
        self.assertEqual((families.registered(self.db, "fcarry"), families.registration_started(self.db, "fcarry")),
                         (False, True))
        self.assertEqual((self.family_batches(), sum(jobs.counts(self.db).values())), ([], 0))
        self.assertIn("registration error: OperationalError('database is locked')",
                      self.events("family.waiting")[-1]["reasons"])
        self.assertEqual(families.unfinished(self.db), ["fcarry"])
        with self.assertRaises(families.FamilyError):                            # registration has started
            families.revoke(self.db, "fcarry", "human:anton", "Anton withdraws F1 for now")
        self.assertEqual(sorted(fleet.strategy_pass(self.db)["registered"]), BASE)
        self.assertEqual([tuple(r) for r in self.db.q("SELECT exp_id, alpha FROM alpha_ledger WHERE note=? ORDER BY "
                                                      "exp_id", "A8 in-sample filter")], [(e, 0.0) for e in BASE])
        self.complete()

    def test_a_stop_after_the_batch_event_queues_the_missing_jobs(self):
        self.ready()
        real, calls = pipeline.enqueue_pipeline, []

        def flaky(db, eid, actor="strategy-1", batch_members=()):
            calls.append(eid)
            if len(calls) == 2:
                raise RuntimeError("the pass stopped")
            return real(db, eid, actor, batch_members)
        with mock.patch.object(pipeline, "enqueue_pipeline", flaky):
            fleet.strategy_pass(self.db)
        self.assertTrue(families.registered(self.db, "fcarry"))
        self.assertEqual([self.jobs_of(e) for e in BASE], [sorted(pipeline.STEPS), [], []])
        self.assertEqual(families.unfinished(self.db), ["fcarry"])
        fleet.strategy_pass(self.db)
        self.complete()

    def test_a_member_already_screening_and_a_void_approval_still_get_the_missing_jobs(self):
        """Review of 4c32ff6, finding 4: enqueue_pipeline queues the 6 jobs in separate transactions and data-1 moves a
        member to SCREENING at once; and a void approval after the batch event must not stop the resume. Otherwise
        cost|E never exists, the other members' validate jobs stay blocked and the family hangs on 'screening'."""
        self.ready()
        real = jobs.enqueue

        def flaky(db, job_id, *a, **k):
            if job_id == f"cost|{L}" and not db.one("SELECT 1 FROM events WHERE kind='test.flaky'"):
                db.event("test.flaky", "fixture", None, {})
                raise RuntimeError("the pass stopped at the 3rd job of member 2")
            return real(db, job_id, *a, **k)
        with mock.patch.object(jobs, "enqueue", flaky):
            fleet.strategy_pass(self.db)
        self.assertTrue(families.registered(self.db, "fcarry"))
        self.assertEqual([len(self.jobs_of(e)) for e in BASE], [6, 2, 0])
        lifecycle.auto_transition(self.db, L, "SCREENING", "system:data-1", "the data step started")   # as data-1 does
        self.blobs["adapter"] = {**self.blobs["adapter"], "committed": "9999", "working": "9999"}
        self.assertIsNone(families.approval(self.db, "fcarry"))               # void after the batch event
        self.assertEqual(families.unfinished(self.db), ["fcarry"])
        self.assertEqual(fleet.strategy_pass(self.db)["registered"], [])
        for e in BASE:
            self.assertEqual(self.jobs_of(e), sorted(pipeline.STEPS), e)
            for d in jobs.get(self.db, f"validate|{e}")["depends_on"]:
                self.assertIsNotNone(jobs.get(self.db, d), d)
        self.assertEqual(families.unfinished(self.db), [])
        self.assertEqual(lifecycle.state(self.db, L), "SCREENING")


class HumanRegisterEdge(A3Base):
    """Finding end-to-end #3: 'lab approve <family instance> REGISTERED' + 'lab confirm' never register a family
    instance, with a void or a valid family approval: lab approve runs the terminal guard and issues no code, lab
    confirm refuses a code issued past it, and so do the dashboard's guards. Only register_batch registers."""

    def test_the_human_registered_edge_is_refused_for_family_instances(self):
        self.ready()
        add_row(self.db, F, 2, built(self.db, F))          # the complete version 2 an interrupted older pass left
        reason = "Anton registers this instance by hand"
        for void in (True, False):
            with self.subTest(void=void):
                self.blobs["vocabulary"]["committed"] = self.blobs["vocabulary"]["working"] = \
                    "changed" if void else CLEAN["vocabulary"]["committed"]
                self.assertEqual(families.approval(self.db, "fcarry") is None, void)
                n = self.db.one("SELECT COUNT(*) FROM approvals")[0]
                rc, text = cli(self.db_path, "approve", F, "REGISTERED", "--reason", reason)
                self.assertEqual(rc, 1, text)
                self.assertIn(families.REGISTER_ONLY_BATCH, text)
                self.assertEqual(self.db.one("SELECT COUNT(*) FROM approvals")[0], n)        # no code was issued
                code = lifecycle.request_approval(self.db, F, "REGISTERED", "human:anton", reason)   # past the guard
                rc, text = cli(self.db_path, "confirm", code)
                self.assertEqual(rc, 1, text)
                self.assertIn(families.REGISTER_ONLY_BATCH, text)
                with self.assertRaises(lifecycle.LifecycleError) as c:
                    lifecycle.confirm(self.db, code, "human:anton@dashboard",
                                      guards=(registry.complete_spec_guard, families.no_web_guard))
                self.assertIn(families.REGISTER_ONLY_BATCH, str(c.exception))
                self.assertEqual(lifecycle.state(self.db, F), "DISCOVERED")
        self.assertIsNone(self.db.one("SELECT 1 FROM transitions WHERE to_state='REGISTERED'"))
        self.assertEqual(sorted(fleet.strategy_pass(self.db)["registered"]), BASE)    # register_batch: one batch


class RegistrationErrorContained(A3Base):
    """Finding engineering #2: an exception while a family registers stays inside that family (one family.waiting
    'registration error', recorded once); the catalogue batch, promotions, holdouts, diagnostics and scan research of
    the strategy pass still run."""

    def test_a_broken_family_never_stops_the_strategy_pass(self):
        pipeline.discover_catalogue(self.db)
        code = templates.request(self.db, "day_of_week", "human:test", "fixture approval for tests")
        templates.confirm(self.db, code, "human:test")
        self.ready()
        ran, real = [], pipeline.enqueue_holdouts
        with mock.patch.object(families, "registration_block", mock.Mock(side_effect=RuntimeError("broken family"))), \
                mock.patch.object(pipeline, "enqueue_holdouts", lambda db, actor="strategy-1": ran.append(1) or
                                  real(db, actor)):
            for _ in range(3):
                st = fleet.strategy_pass(self.db)
                self.assertTrue({"promotions", "holdouts_queued", "diagnostics_queued", "scan_research_queued"} <=
                                set(st), st)
        self.assertEqual(len(ran), 3)
        self.assertEqual(lifecycle.state(self.db, "E_day_of_week_p2"), "REGISTERED")    # the catalogue batch ran
        self.assertEqual({lifecycle.state(self.db, e) for e in BASE}, {"DISCOVERED"})
        w = [x for x in self.events("family.waiting") if x["reasons"][0].startswith("registration error")]
        self.assertEqual(w, [{"family": "fcarry", "reasons": ["registration error: RuntimeError('broken family')"]}])


class FamilyCliTexts(A3Base):
    """Finding end-to-end #6: confirm-family states amendment 9's dates (registration and the train/validation spot
    downloads until 2026-10-24 00:00 UTC, then a wait until 2026-11-28), and a refusal says 'refused:' once."""

    def test_confirm_family_states_the_amendment_9_dates(self):
        import argparse
        from lab.__main__ import family_cmd
        families.discover_all(self.db)
        self.revive()
        code = families.request(self.db, "fcarry", "human:anton", "Anton approves F1 after reading it")
        answers, lines = iter([code, "abcdef01"]), []
        rc = family_cmd(argparse.Namespace(cmd="confirm-family"), self.db, lines.append, ask=lambda q: next(answers))
        self.assertEqual(rc, 0, lines)
        self.assertIn("spot downloads are allowed until 2026-10-24 00:00 UTC", lines[-1])
        self.assertIn("waits until 2026-11-28 00:00 UTC", lines[-1])
        self.assertNotIn("not before 2026-11-28 if data must be downloaded", lines[-1])

    def test_a_refusal_says_refused_once(self):
        import argparse
        from lab.__main__ import family_cmd
        families.discover_all(self.db)
        rc, text = cli(self.db_path, "approve", F, "DISCOVERED", "--reason", WHY)
        self.assertEqual(rc, 0, text)
        code, lines = text.split(": ")[1].split()[0], []
        self.p[0].stop()                                                          # the real guard
        try:
            with mock.patch.dict(os.environ, {"CLAUDECODE": "1"}):
                rc, text = cli(self.db_path, "confirm", code)
                rc2 = family_cmd(argparse.Namespace(cmd="confirm-family"), self.db, lines.append,
                                 ask=lambda q: self.fail("asked for a code"))
        finally:
            self.p[0].start()
        self.assertEqual((rc, rc2, lifecycle.state(self.db, F)), (1, 1, "SUPPRESSED"))
        for t in (text, "\n".join(lines)):
            self.assertEqual(t.count("refused:"), 1, t)
            self.assertIn("refused: an assistant session may not take a human step of an amendment 8 family", t)


class CodePinBindsTheApproval(A5Base):
    """Code pin, amendment 8 point 18 / design test 26: before every step of a family instance the spec's code_blobs
    must be the blobs of the approval its registration cited (not the spec compared with itself), every engine file
    must have a recorded blob, the spec must be the registered version 2, and the working family file and module must
    still be the registered blobs (CodePin above); otherwise the step fails closed and nothing is regenerated."""

    def test_the_spec_is_pinned_to_the_cited_approval_and_its_registered_version(self):
        self.register()
        spec, cited = pipeline._spec(self.db, F), families.cited_approval(self.db, F)
        self.assertEqual(cited["event_id"], families.approval(self.db, "fcarry"))
        self.assertEqual(families.pin_problems(spec, cited), [])
        for k in families.BOUND:
            with self.subTest(k):
                bad = families.pin_problems({**spec, "code_blobs": {**spec["code_blobs"], k: "another-blob"}}, cited)
                self.assertTrue(any(f"code_blobs.{k} is not the blob the family approval bound" in b for b in bad), bad)
        bad = families.pin_problems({**spec, "code_blobs": {**spec["code_blobs"], "lab/pipeline.py": None}}, cited)
        self.assertTrue(any("no recorded blob of lab/pipeline.py" in b for b in bad), bad)
        self.assertTrue(families.pin_problems(spec, None))                       # no approval cited: fails closed
        self.assertTrue(families.pin_problems(spec, {**cited, "family": "other"}))
        add_row(self.db, F, 3, {**spec, "costs": ZERO})                         # a later version, past add-version
        for step in (pipeline.step_data, pipeline.step_backtest, pipeline.step_report):
            with self.subTest(step.__name__):
                with self.assertRaises(pipeline.StepError) as c:
                    step(self.db, {"exp_id": F}, "worker-1")
                self.assertIn("not the registered version 2", str(c.exception))
        self.assertEqual(lifecycle.state(self.db, F), "REGISTERED")
        self.assertIsNone(self.db.one("SELECT 1 FROM datasets WHERE exp_id=?", F))
        self.assertFalse(os.path.exists(os.path.join(pipeline.ARTIFACTS, F)))   # nothing was regenerated
        self.assertTrue(any("is not the registered version 2" in b for b in families.family_pin(self.db, "fcarry")))


# ---------- verifier findings of 2026-10-19, group 2: results, forward outcome, paper, alpha budget (points 3-16) -----
class ForwardDecisionsOnlyFromTheSteps(A5Base):
    """Finding protocol-statistics #2 (PoCs CliBypass C1 and C2): lab result refuses family instances, and every gate
    edge of a family instance (lab transition and the steps alike) passes families.gate_problem: never SCREENING ->
    SCREEN_PASSED, a result recorded by a step, and OBSERVATION is left only on a forward result of the member's cohort
    (its cohort id and hash-matching observe.json or observe_interim.json) or a 'not selected' result. forward_outcome
    and forward_passes count nothing else, so a forged PASS neither closes the family nor lifts the programme stop."""

    def test_lab_result_and_lab_transition_never_move_a_family_instance(self):
        self.register()
        lifecycle.auto_transition(self.db, F, "SCREENING", "system:fixture", "screening starts in this test")
        with mock.patch.dict(os.environ, {"CLAUDECODE": "1"}), \
                mock.patch.object(families, "GUARD", families.interactive_human):
            rc, text = cli(self.db_path, "result", F, "--label", "EXPLORATORY", "--verdict", "PASS forged by the CLI")
            self.assertEqual(rc, 1, text)                                       # PoC C1 recorded it
            self.assertIn("family instance: its results are recorded only by its steps", text)
            self.assertIsNone(self.db.one("SELECT 1 FROM results WHERE exp_id=?", F))
            rid = registry.record_result(self.db, F, "EXPLORATORY", "PASS (screen): a row past lab result", {}, {},
                                         "system:fixture")
            rc, text = cli(self.db_path, "transition", F, "SCREEN_PASSED", "--reason",
                           "forged straight to SCREEN_PASSED", "--result-id", str(rid))
            self.assertEqual(rc, 1, text)                                       # PoC C1 moved it
            self.assertIn("never goes directly to SCREEN_PASSED", text)
            typed = self.db.append("results", exp_id=F, version=2, ts=0, label="EXPLORATORY",
                                   verdict=families.OBSERVE + ": typed past lab result", metrics={}, evidence={})
            self.db.event("result.recorded", "human:anton", F, {"result_id": typed, "label": "EXPLORATORY"})
            rc, text = cli(self.db_path, "transition", F, "OBSERVATION", "--reason", "forged into the forward test",
                           "--result-id", str(typed))
            self.assertEqual(rc, 1, text)
            self.assertIn("cites a result recorded by its step", text)
        with self.assertRaises(registry.RegistryError):
            registry.record_result(self.db, F, "EXPLORATORY", "PASS forged in Python", {}, {}, "human:anton")
        self.assertEqual(lifecycle.state(self.db, F), "SCREENING")
        self.assertIsNone(self.db.one("SELECT 1 FROM transitions WHERE to_state IN ('SCREEN_PASSED', 'OBSERVATION')"))
        self.assertEqual(self.screened(L)["state"], "OBSERVATION")             # the report step's own edge still works

    def test_a_forged_forward_pass_neither_closes_the_family_nor_lifts_the_programme_stop(self):
        self.register()
        self.screened(F, sharpe=1.5)
        for e in (L, H):
            self.screened(e, observe=False)
        fleet.strategy_pass(self.db)
        cf = families.cohort(self.db, "fcarry")
        self.assertEqual(cf["selected"], [F])
        with mock.patch.dict(os.environ, {"CLAUDECODE": "1"}):
            rc, text = cli(self.db_path, "result", F, "--label", "VALIDATION", "--verdict",
                           families.FORWARD_PASS + ": forged")
        self.assertEqual(rc, 1, text)
        forged = pipeline.save_artifact(F, "observe", {"forged": True})
        for metrics, evidence in (({}, {}), ({"cohort": cf["cohort"]}, {}),          # rows past lab result
                                  ({"cohort": "fcarry:fwd209901m12"}, {"artifacts": [forged]}),
                                  ({"cohort": cf["cohort"]}, {"artifacts": [dict(forged, sha256="0" * 64)]})):
            with self.subTest(metrics=metrics, evidence=evidence):
                rid = registry.record_result(self.db, F, "VALIDATION", families.FORWARD_PASS + ": forged", metrics,
                                             evidence, "system:fixture")
                rc, text = cli(self.db_path, "transition", F, "SCREEN_PASSED", "--reason",
                               "forged forward pass, no window was read", "--result-id", str(rid))
                self.assertEqual(rc, 1, text)                                   # PoC C2 moved it
                self.assertIn("needs a forward result of the cohort that selected it", text)
                self.assertIsNone(families.forward_outcome(self.db, F))
        self.assertEqual(lifecycle.state(self.db, F), "OBSERVATION")
        self.assertEqual(families.forward_passes(self.db), set())
        st = self.status()
        self.assertTrue(st.startswith("forward test"), st)                    # PoC C2: 'closed: PASS'
        self.assertIsNone(families.closed(self.db, "fcarry"))
        self.now[0] = ts(2028, 7, 2)
        self.assertTrue(families.programme_stop(self.db))                      # PoC C2: [] (the stop lifted)


class NoPaperTradingForFamilies(A3Base):
    """Finding protocol-statistics #7 (PoC HumanPaper): a family instance never enters PAPER_TRADING (point 16: a live
    spot feed and a later amendment first). lab approve issues no code, lab confirm and the dashboard refuse a code
    issued past the guard, from VALIDATED and from PAUSED, and promotion.trading_authorized refuses a family instance
    even in PAPER_TRADING."""

    def test_a_validated_or_paused_family_instance_is_never_authorized_to_trade(self):
        self.ready()
        fleet.strategy_pass(self.db)
        e, reason = L, "paper trade the family please"
        for st in ("SCREENING", "OBSERVATION", "SCREEN_PASSED", "VALIDATION"):
            self.db.append("transitions", exp_id=e, ts=0, from_state=None, to_state=st, actor="fixture",
                           reason="fixture: the path to a holdout")
        rid = registry.record_result(self.db, e, "VALIDATION", "PASS (holdout): fixture", {}, {}, "system:fixture")
        self.db.append("transitions", exp_id=e, ts=0, from_state="VALIDATION", to_state="VALIDATED", actor="fixture",
                       reason="fixture: holdout passed", evidence={"result_id": rid})
        n = self.db.one("SELECT COUNT(*) FROM approvals")[0]
        rc, text = cli(self.db_path, "approve", e, "PAPER_TRADING", "--reason", reason)
        self.assertEqual(rc, 1, text)
        self.assertIn(families.NO_PAPER, text)
        self.assertEqual(self.db.one("SELECT COUNT(*) FROM approvals")[0], n)          # no code was issued
        code = lifecycle.request_approval(self.db, e, "PAPER_TRADING", "human:anton", reason)   # past the guard
        with self.assertRaises(lifecycle.LifecycleError) as c:                         # PoC HumanPaper's call
            lifecycle.confirm(self.db, code, "human:anton", guards=(registry.complete_spec_guard,
                                                                     families.terminal_guard))
        self.assertIn(families.NO_PAPER, str(c.exception))
        rc, text = cli(self.db_path, "confirm", code)
        self.assertEqual(rc, 1, text)
        with self.assertRaises(lifecycle.LifecycleError) as c:
            lifecycle.confirm(self.db, code, "human:anton@dashboard", guards=(registry.complete_spec_guard,
                                                                               families.no_web_guard))
        self.assertIn(families.NO_PAPER, str(c.exception))
        self.assertEqual(lifecycle.state(self.db, e), "VALIDATED")
        lifecycle.confirm(self.db, code, "human:anton", guards=(registry.complete_spec_guard,))  # past every guard
        self.assertEqual(lifecycle.state(self.db, e), "PAPER_TRADING")
        self.assertEqual(promotion.trading_authorized(self.db, e), (False, f"{e}: {families.NO_PAPER}"))  # PoC: True
        self.db.append("transitions", exp_id=e, ts=0, from_state="PAPER_TRADING", to_state="PAUSED",
                       actor="system:risk-1", reason="fixture: paused by a risk rule")
        rc, text = cli(self.db_path, "approve", e, "PAPER_TRADING", "--reason", reason, "--committed",
                       "research/PROTOCOL_V3.md")
        self.assertEqual(rc, 1, text)
        self.assertIn(families.NO_PAPER, text)
        self.assertEqual(lifecycle.state(self.db, e), "PAUSED")


class AlphaSumsOnlyA8Rows(A3Base):
    """Finding protocol-statistics #3 (PoC BudgetPrefix): families.alpha_reserved and reserved(fid) sum only the
    amendment 8 rows (A8 reserve, spend and release of family:<fid>, A8 spend of instances). The PoC's family:zzz is
    refused at lab discover, so lab add-version has nothing to version, and a negative row under any family-like id
    written past them changes neither sum: W0 still refuses a fifth family. Budget above is the property test."""

    def test_a_foreign_negative_row_never_frees_programme_wealth(self):
        rc, text = cli(self.db_path, "discover", "family:zzz", "--hypothesis", "h", "--mechanism", "m", "--instrument",
                       "i", "--horizon", "days", "--execution", "taker", "--source", "s")
        self.assertEqual(rc, 1, text)
        path = os.path.join(self.tmp, "neg.json")
        with open(path, "w") as f:
            json.dump(dict({k: "x" for k in registry.REQUIRED_SPEC}, code="lab/engine/data.py", alpha="-0.05"), f)
        rc, text = cli(self.db_path, "add-version", "family:zzz", "--spec", path)
        self.assertEqual(rc, 1, text)
        self.assertIsNone(self.db.one("SELECT 1 FROM alpha_ledger"))
        for e, note in (("family:zzz", "version 2"), ("family:fcarry", "version 2"), (F, "version 2"),
                        ("family:fcarry", "exploratory screening"), ("FAMILY:fcarry", "A8 reserve"),
                        ("E_screen_x", "A8 spend")):
            self.db.append("alpha_ledger", exp_id=e, ts=0, alpha=-0.05, note=note)
        self.assertEqual((families.alpha_reserved(self.db), families.reserved(self.db, "fcarry")), (0, 0))
        for fid in ("fa", "fb", "fc", "fd"):                                   # four families hold W0 = 0.05
            self.db.append("alpha_ledger", exp_id=f"family:{fid}", ts=0, alpha=0.0125, note="A8 reserve")
        self.assertAlmostEqual(families.alpha_reserved(self.db), 0.05)
        families.discover_all(self.db)
        self.revive()
        with self.assertRaises(families.FamilyError) as c:                     # PoC BudgetPrefix approved a fifth
            self.approve()
        self.assertIn("alpha budget", str(c.exception))
        self.assertIsNone(families.approval(self.db, "fcarry"))
        self.assertAlmostEqual(families.alpha_reserved(self.db), 0.05)


class AlphaFReservedOncePerFamily(A5Base):
    """Finding protocol-statistics #4 (PoCs DoubleReserve A and A2): alpha_F is reserved once per family. A second
    approval is refused while the family holds its reservation and its last approval event is not a revocation (also
    for a second code confirmed after the first); a void approval is revoked, which releases the reservation, before it
    is approved again; and fix_cohort releases what a family holds above alpha_F (a second reservation written before
    this fix) with an 'A8 release' row."""

    def test_a_second_approval_is_refused_while_the_reservation_is_held(self):
        families.discover_all(self.db)
        self.revive()
        codes = [families.request(self.db, "fcarry", "human:anton", "Anton approves F1 after reading it")
                 for _ in range(2)]                                            # two codes before any confirm
        families.confirm(self.db, codes[0], "abcdef01", "human:anton")
        with self.assertRaises(families.FamilyError) as c:
            families.confirm(self.db, codes[1], "abcdef01", "human:anton")
        self.assertIn("already holds its alpha_F reservation", str(c.exception))
        with self.assertRaises(families.FamilyError):                         # PoC A: a second request and confirm
            self.approve()
        self.assertEqual(self.ledger(), [("family:fcarry", 0.0125, "A8 reserve")])
        self.assertEqual(len(self.events("family.approved")), 1)
        self.touch()
        self.assertEqual(sorted(fleet.strategy_pass(self.db)["registered"]), BASE)
        self.screened(F, sharpe=1.5)
        for e in (L, H):
            self.screened(e, observe=False)
        self.assertTrue(self.status().startswith("forward test: cohort fcarry:fwd202612m12, M 1"))
        self.assertAlmostEqual(families.reserved(self.db, "fcarry"), 0.0)
        self.assertAlmostEqual(families.alpha_reserved(self.db), 0.0125)      # PoC A: 0.025, held for good

    def test_a_void_approval_is_revoked_before_it_is_approved_again(self):
        self.ready()
        self.blobs["family"] = {**self.blobs["family"], "committed": "abcdef01ffff", "working": "abcdef01ffff"}
        self.assertIsNone(families.approval(self.db, "fcarry"))               # void: a bound file changed
        with self.assertRaises(families.FamilyError) as c:                     # PoC A2 reserved alpha_F again here
            self.approve()
        self.assertIn("revoke-family first", str(c.exception))
        self.assertAlmostEqual(families.revoke(self.db, "fcarry", "human:anton", "Anton withdraws the void approval"),
                               0.0125)
        self.approve()
        self.assertEqual(self.ledger(), [("family:fcarry", 0.0125, "A8 reserve"),
                                         ("family:fcarry", -0.0125, "A8 release"),
                                         ("family:fcarry", 0.0125, "A8 reserve")])
        self.assertAlmostEqual(families.reserved(self.db, "fcarry"), 0.0125)
        self.assertEqual(sorted(fleet.strategy_pass(self.db)["registered"]), BASE)

    def test_the_cohort_releases_a_reservation_above_alpha_f(self):
        self.register()
        self.db.append("alpha_ledger", exp_id="family:fcarry", ts=0, alpha=0.0125, note="A8 reserve")  # before the fix
        self.screened(F, sharpe=1.5)
        for e in (L, H):
            self.screened(e, observe=False)
        self.assertTrue(self.status().startswith("forward test: cohort fcarry:fwd202612m12, M 1"))
        self.assertEqual(self.ledger()[-3:], [("family:fcarry", -0.0125, "A8 spend"), (F, 0.0125, "A8 spend"),
                                              ("family:fcarry", -0.0125, "A8 release")])
        self.assertAlmostEqual(families.cohort(self.db, "fcarry")["alpha_excess_released"], 0.0125)
        self.assertAlmostEqual(families.reserved(self.db, "fcarry"), 0.0)
        self.assertAlmostEqual(families.alpha_reserved(self.db), 0.0125)


class PerTagLimits(A3Base):
    """Finding protocol-statistics #5 (PoC PerTag), amendment 8 point 3: at most 2 families per canonical tag in the
    whole programme and at most 1 open family per tag at a time, at approval (request and confirm) and at registration
    (registration_block). At approval an approved family that has not registered yet is open; at registration only the
    registered ones are, so two approvals from before the rule never block each other."""

    def earlier(self, fid, closed_as=None):
        """An earlier family on fcarry's tag with one registered instance: closed (REJECTED) or still screening."""
        e = f"E_{fid}__x1_a8"
        self.db.append("experiments", exp_id=e, version=1, created_ts=0, mechanism_tag="delta_neutral_funding_carry",
                       fingerprint=e, spec_json={"execution": "taker", "family": fid})
        for st in ("REGISTERED", "SCREENING") + (("REJECTED",) if closed_as else ()):
            self.db.append("transitions", exp_id=e, ts=0, from_state=None, to_state=st, actor="fixture",
                           reason="fixture: an earlier family on the same tag")
        if closed_as:
            self.db.event("family.closed", "system:fixture", None, {"family": fid, "outcome": closed_as})
        return e

    def acked(self, *eids):
        """fcarry's file with graveyard acknowledgements of the earlier families' rejected instances."""
        real = families.load

        def load(path_or_fid):
            fam = real(path_or_fid)
            if fam.get("family_id") == "fcarry":
                fam["graveyard_acknowledged"] = fam["graveyard_acknowledged"] + [
                    {"exp_id": e, "match": "exact", "lessons_addressed": ["x"],
                     "materially_different_because": "materially different because a later, separately drafted family"}
                    for e in eids]
            return fam
        return mock.patch.object(families, "load", load)

    def test_at_most_two_families_per_tag_in_the_whole_programme(self):
        gone = [self.earlier(fid, "FUTILE_IN_SAMPLE") for fid in ("fone", "ftwo")]
        with self.acked(*gone):
            families.discover_all(self.db)
            self.revive()
            with self.assertRaises(families.FamilyError) as c:                # PoC PerTag approved a third family
                self.approve()
            self.assertIn("at most 2 families per canonical tag in the whole programme: delta_neutral_funding_carry "
                          "already has fone, ftwo", str(c.exception))
            force_approval(self.db)                                            # an approval from before the rule
            self.touch()
            self.assertEqual(fleet.strategy_pass(self.db)["registered"], [])  # PoC PerTag registered the base batch
            why = self.events("family.waiting")[-1]["reasons"]
            self.assertTrue(any(r.startswith("at most 2 families per canonical tag") for r in why), why)
        self.assertFalse(families.registration_started(self.db, "fcarry"))

    def test_at_most_one_open_family_per_tag_at_a_time(self):
        e = self.earlier("fone")                                               # registered, still screening
        families.discover_all(self.db)
        self.revive()
        with self.assertRaises(families.FamilyError) as c:
            self.approve()
        self.assertIn("at most 1 open family per tag at a time: fone on delta_neutral_funding_carry is not closed",
                      str(c.exception))
        force_approval(self.db)                                                # an approval from before the rule
        self.touch()
        self.assertEqual(fleet.strategy_pass(self.db)["registered"], [])
        why = self.events("family.waiting")[-1]["reasons"]
        self.assertTrue(any(r.startswith("at most 1 open family per tag") for r in why), why)
        self.db.append("transitions", exp_id=e, ts=0, from_state="SCREENING", to_state="REJECTED", actor="fixture",
                       reason="fixture: the earlier family's instance was rejected")
        self.db.event("family.closed", "system:fixture", None, {"family": "fone", "outcome": "FUTILE_IN_SAMPLE"})
        with self.acked(e):                                                    # one other family on the tag, closed
            self.assertEqual(sorted(fleet.strategy_pass(self.db)["registered"]), BASE)

    def test_an_approved_family_is_open_at_approval_but_not_at_registration(self):
        self.ready()                                                           # fcarry approved, not registered
        other = dict(copy.deepcopy(FCARRY), family_id="fcarr2")
        self.assertEqual(families.tag_problems(self.db, other), [
            "at most 1 open family per tag at a time: fcarry on delta_neutral_funding_carry is not closed (amendment 8 "
            "point 3)"])
        self.assertEqual(families.tag_problems(self.db, other, registration=True), [])
        self.assertEqual(families.tag_problems(self.db, FCARRY), [])           # a family never counts itself


# ---------- verifier findings of 2026-10-19, group 3: robustness and protocol conformance ----------
class InterimLookResumesAfterACrash(ForwardBase):
    """Finding engineering #3: the forward steps are idempotent across a crash or a lost lease. A retry of the interim
    look after its 'continue' event (re)queues the final test; after its futility result it rejects with that result,
    and once rejected it completes instead of failing for good on 'requires lifecycle OBSERVATION' (which stopped the
    family without closing its cohort). The final forward test resumes the same way. Nothing is read or recorded
    twice, and the look still runs once."""

    def run_interim_job(self):
        jid = f"observe_interim|{F}"
        with self.db.tx():                                     # due now (the queue's clock is the real one), or put
            self.db.con.execute("UPDATE jobs SET status='queued', next_run=0, lease_owner=NULL WHERE job_id=?",
                                (jid,))                        # back by _expire after a lost lease
        [a for a in fleet.agents(self.db_path) if a.name == "validation-1"][0](self.db)
        return jobs.get(self.db, jid)

    def test_a_crash_between_the_continue_event_and_the_final_job_is_completed_by_the_retry(self):
        cf = self.cohort_of_one()
        self.now[0] = cf["interim_not_before"]
        with mock.patch.object(jobs, "enqueue", mock.Mock(side_effect=RuntimeError("the worker died"))):
            self.assertEqual(self.run_interim_job()["status"], "queued")      # a retry; the event was written
        ev = self.events("family.interim")
        self.assertEqual((len(ev), ev[0]["outcome"], jobs.get(self.db, f"observe|{F}")), (1, "continue", None))
        n = self.reads()
        j = self.run_interim_job()
        self.assertEqual(j["status"], "done", j["error"])                       # failed for good before ('runs once')
        self.assertEqual(j["result"]["verdict"], pipeline.INTERIM_CONTINUE)
        fin = jobs.get(self.db, f"observe|{F}")
        self.assertEqual((fin["kind"], fin["status"], fin["next_run"], fin["payload"]),
                         ("observe", "queued", cf["final_not_before"], {"start": cf["start"], "months": 12,
                                                                        "cohort": cf["cohort"]}))
        self.assertEqual(pipeline.frozen_artifact(self.db, F, "observe_interim")["window"], "fwd202612m06")
        self.assertEqual(self.interim()["verdict"], pipeline.INTERIM_CONTINUE)    # idempotent
        self.assertEqual((self.reads(), len(self.events("family.interim"))), (n, 1))
        self.assertTrue(self.status().startswith(f"forward test: cohort {cf['cohort']}"))

    def test_a_lost_lease_after_the_futility_rejection_never_stops_the_family(self):
        cf = self.cohort_of_one()
        self.now[0] = cf["interim_not_before"]
        with mock.patch.object(fcarry, "carry_filter", never):
            with mock.patch.object(jobs, "complete", lambda *a, **k: False):   # the lease was lost: result discarded
                self.run_interim_job()
            rid = self.db.one("SELECT id FROM results WHERE exp_id=? AND label='VALIDATION'", F)[0]
            self.assertEqual(lifecycle.state(self.db, F), "REJECTED")
            n = self.reads()
            j = self.run_interim_job()
        self.assertEqual(j["status"], "done", j["error"])                       # failed for good before
        self.assertEqual((j["result"]["result_id"], j["result"]["state"]), (rid, "REJECTED"))
        self.assertEqual(self.db.one("SELECT COUNT(*) FROM results WHERE exp_id=? AND label='VALIDATION'", F)[0], 1)
        self.assertEqual(self.reads(), n)
        self.assertIsNone(jobs.get(self.db, f"observe|{F}"))
        self.assertEqual(self.status(), "closed: FAIL")          # before: 'stopped: 1 job(s) failed permanently'
        self.assertEqual(self.ledger()[-1], (F, 0.0125, "A8 spend"))

    def test_a_crash_between_the_futility_result_and_the_rejection_reuses_the_result(self):
        cf = self.cohort_of_one()
        self.now[0] = cf["interim_not_before"]
        with mock.patch.object(fcarry, "carry_filter", never):
            with mock.patch.object(lifecycle, "auto_transition", mock.Mock(side_effect=RuntimeError("worker died"))):
                with self.assertRaises(RuntimeError):
                    self.interim()
            self.assertEqual(lifecycle.state(self.db, F), "OBSERVATION")
            n = self.reads()
            out = self.interim()
        rows = [r[0] for r in self.db.q("SELECT id FROM results WHERE exp_id=? AND label='VALIDATION'", F)]
        self.assertEqual((len(rows), out["result_id"], out["state"], lifecycle.state(self.db, F)),
                         (1, rows[0], "REJECTED", "REJECTED"))
        self.assertEqual(self.reads(), n)
        self.assertEqual(families.forward_outcome(self.db, F), "FAIL")

    def test_the_final_forward_test_resumes_the_same_way(self):
        cf = self.cohort_of_one()
        self.now[0] = cf["interim_not_before"]
        self.interim()
        self.now[0] = cf["final_not_before"]
        with mock.patch.object(lifecycle, "auto_transition", mock.Mock(side_effect=RuntimeError("worker died"))):
            with self.assertRaises(RuntimeError):
                self.final()
        self.assertEqual(lifecycle.state(self.db, F), "OBSERVATION")
        n = self.reads()
        out, again = self.final(), self.final()            # the second: 'requires lifecycle OBSERVATION' before
        rows = [r[0] for r in self.db.q("SELECT id FROM results WHERE exp_id=? AND label='VALIDATION'", F)]
        self.assertEqual((len(rows), out["result_id"], again["result_id"]), (1, rows[0], rows[0]))
        self.assertEqual((out["state"], again["state"], lifecycle.state(self.db, F)), ("SCREEN_PASSED",) * 3)
        self.assertEqual(self.reads(), n)
        self.assertEqual(self.status(), "closed: PASS")


class DeferredJobsLetIdleAgentsSleep(A3Base):
    """Finding engineering #4 (PoC DeferInFleet): after an embargo deferral the downstream jobs of the deferred data
    steps cannot unblock before it runs, so jobs.runnable_any no longer counts them and idle backtest, cost, adversarial,
    validation and report agents skip the write-locked claim() until 2026-11-28. A blocked job that can unblock, a due
    job and an expired lease anywhere still count (0979ef7; test_lab_step1)."""

    def test_jobs_blocked_behind_a_deferred_job_are_not_runnable(self):
        self.queue_on_the_fixture_clock()
        self.now[0] = ts(2026, 10, 20)
        self.ready(files=False)
        self.touch(kinds=("klines", "funding"))
        self.assertEqual(sorted(fleet.strategy_pass(self.db)["registered"]), BASE)
        self.now[0] = ts(2026, 10, 25)                                         # the embargo started before the data step
        agent = [a for a in fleet.agents(self.db_path) if a.name == "data-1"][0]
        for _ in BASE:
            agent(self.db)
        until = max(jobs.get(self.db, f"data|{e}")["next_run"] for e in BASE)
        self.assertEqual(self.db.one("SELECT COUNT(*) FROM jobs WHERE status='blocked'")[0], 15)
        kinds = {a.name: a.kinds for a in fleet.agents(self.db_path) if a.kinds}
        for name in ("data-1", "backtest-1", "cost-1", "adversarial-1", "validation-1", "report-1"):
            self.assertFalse(jobs.runnable_any(self.db, kinds[name], now=until - 1), name)   # PoC: True for backtest
        self.assertIsNone(jobs.claim(self.db, "backtest-1", ("backtest",), now=until - 1))
        for name in ("data-1", "backtest-1", "cost-1", "validation-1"):        # the deferral ends: claim may unblock
            self.assertTrue(jobs.runnable_any(self.db, kinds[name], now=until), name)
        jobs.enqueue(self.db, "diagnose|X", "diagnose", "X", {})
        jobs.claim(self.db, "report-1", ("diagnose",))
        with self.db.tx():
            self.db.con.execute("UPDATE jobs SET lease_until=0 WHERE job_id='diagnose|X'")
        self.assertTrue(jobs.runnable_any(self.db, ("backtest",), now=until - 1))   # an expired lease anywhere


class DelistedCoinsLeaveFromTheDayAfter(ForwardBase):
    """Finding protocol-statistics #8 (survivorship): amendment 8 point 11 cites amendment 7 point 5, which excludes a
    coin delisted in the window from the day after. The family forward split keeps its data up to its last listed hour
    (the same quality rule over those hours), closes its position there (the exit is charged) and gives the weight to
    the rest; a gap followed by more data is no delisting. The data-quality gate is not loosened: min_symbols still
    counts only coins with the whole window. A forward window's 404 is never remembered."""

    def delist(self, cf, sym, first, kinds=("klines", "funding", "spot")):
        for kind, pairs in data.expected_paths(sym, cf["window"], spot=True).items():
            for u, p in pairs[first:]:
                if kind in kinds:
                    os.remove(p)
                    families._mark_absent(u)                   # the fixture's archive answers 404 (data._fetch mock)

    def forward(self, cf, spec):
        self.now[0] = cf["final_not_before"]
        return pipeline._forward_market(self.db, F, "validation-1", spec, families.FORWARD_MONTHS)[2]

    def test_a_delisted_coin_counts_until_its_last_listed_hour_and_then_is_flat(self):
        cf = self.cohort_of_one()
        self.delist(cf, "LINKUSDT", 4)                                         # delisted from 2027-04
        spec = pipeline._spec(self.db, F)
        with mock.patch.object(fcarry, "carry_filter", always), \
                mock.patch.object(pipeline, "_evaluate", wraps=pipeline._evaluate) as ev, \
                mock.patch.object(pipeline, "_bench", wraps=pipeline._bench) as be:
            f = self.forward(cf, spec)
        last = ts(2027, 3, 31, 23)
        self.assertEqual((f["excluded"], f["symbols"], f["enough"]), ([], sorted(SIX), True))
        self.assertEqual(f["delisted"], {"LINKUSDT": {"last_listed_hour": last, "excluded_from": "2027-04-01"}})
        bars, funding, pos = ev.call_args_list[0][0][:3]
        self.assertEqual((bars["LINKUSDT"][-1][0], max(funding["LINKUSDT"])), (last, last - 7 * HOUR))
        self.assertEqual((pos["LINKUSDT"][-2:], pos["BNBUSDT"][-1]), ([1.0, 0.0], 1.0))   # closed at its last hour
        fd = be.call_args_list[0][0][3]
        self.assertEqual((fd.perp["LINKUSDT"][-1][0], max(fd.funding["LINKUSDT"])), (last, last - 7 * HOUR))
        self.assertEqual(f["quality"]["LINKUSDT"]["listed_until"], last)
        with mock.patch.object(fcarry, "carry_filter", always):               # not loosened: 5 whole-window coins
            self.assertFalse(self.forward(cf, {**spec, "min_symbols": 6})["enough"])
            self.assertTrue(self.forward(cf, {**spec, "min_symbols": 5})["enough"])
        self.delist(cf, "LTCUSDT", 2, kinds=("spot",))                          # the spot leg delisted from 2027-02
        with mock.patch.object(fcarry, "carry_filter", always):
            f = self.forward(cf, spec)
            self.assertFalse(self.forward(cf, {**spec, "min_symbols": 5})["enough"])   # LINK and LTC never count
        self.assertEqual(sorted(f["delisted"]), ["LINKUSDT", "LTCUSDT"])
        self.assertEqual(f["delisted"]["LTCUSDT"]["excluded_from"], "2027-02-01")

    def test_a_month_published_for_no_coin_is_a_delay_not_a_delisting(self):
        """Review of fdd898a (engineering #5b): the archive has not published the window's last month for any coin
        yet: the forward test waits a day and decides nothing, instead of treating every coin as delisted."""
        cf = self.cohort_of_one()
        for s in SIX:
            self.delist(cf, s, 11)                                             # 2027-11 missing for every coin
        with self.assertRaises(pipeline.Deferred) as c:
            self.forward(cf, pipeline._spec(self.db, F))
        self.assertIn("has not published 2027-11", str(c.exception))
        self.assertTrue(any("has not published" in r for w in self.events("family.waiting") for r in w["reasons"]))
        self.assertIsNone(self.db.one("SELECT 1 FROM results WHERE exp_id=? AND label='VALIDATION'", F))

    def test_a_gap_followed_by_more_data_is_no_delisting(self):
        cf = self.cohort_of_one()
        for kind, pairs in data.expected_paths("LINKUSDT", cf["window"], spot=True).items():
            u, p = pairs[2]                                                    # 2027-02 missing, 2027-03 on
            os.remove(p)
            families._mark_absent(u)
        f = self.forward(cf, pipeline._spec(self.db, F))
        self.assertEqual((f["excluded"], f["delisted"]), (["LINKUSDT"], {}))   # the quality rule, as before
        self.assertNotIn("LINKUSDT", f["symbols"])
        self.assertFalse(f["quality"]["LINKUSDT"]["ok"])

    def test_a_forward_404_is_never_remembered(self):
        self.now[0] = ts(2027, 12, 8)
        url, asked = f"{data.SPOT_BASE}/klines/LINKUSDT/1h/LINKUSDT-1h-2027-11.zip", []

        def gone(u):
            asked.append(u)
            raise urllib.error.HTTPError(u, 404, "not found", None, None)
        for _ in range(2):
            with self.assertRaises(urllib.error.HTTPError):
                families.guarded_get("fwd202612m12", fetch=gone)(url)
        self.assertEqual((asked, url in families.absent()), ([url, url], False))   # a late monthly file is fetched
        families._mark_absent(url)                                               # a 404 remembered before the fix
        with self.assertRaises(urllib.error.HTTPError):
            families.guarded_get("fwd202612m12", fetch=gone)(url)
        self.assertEqual(len(asked), 3)
        screen = f"{data.SPOT_BASE}/klines/LINKUSDT/1h/LINKUSDT-1h-2022-01.zip"   # the screening splits remember
        with self.assertRaises(urllib.error.HTTPError):
            families.guarded_get("train3", fetch=gone)(screen)
        self.assertIn(screen, families.absent())



class ReportStepResumesAfterACrash(A5Base):
    """Review of 4c32ff6, finding 5: the report step records its result and takes its edge before jobs.complete. A retry
    of a family instance's report job (a crash, a lost lease) completes what the first run recorded, records nothing
    twice, and never fails for good on 'requires lifecycle SCREENING' (a failed report job stops the family for good
    and leaves alpha_F reserved)."""

    def results(self):
        return self.db.one("SELECT COUNT(*) FROM results")[0]

    def test_a_rerun_report_after_its_edge_records_nothing_and_returns_the_first_result(self):
        self.register()
        first = {F: self.screened(F, sharpe=1.5), L: self.screened(L, observe=False)}
        n = self.results()
        for e, r in first.items():
            again = pipeline.step_report(self.db, {"exp_id": e}, "report-1")
            self.assertEqual((again["result_id"], again["state"], again["verdict"], again.get("resumed")),
                             (r["result_id"], r["state"], r["verdict"], True), e)
        self.assertEqual((lifecycle.state(self.db, F), lifecycle.state(self.db, L)), ("OBSERVATION", "REJECTED"))
        self.assertEqual(self.results(), n)

    def test_a_crash_between_the_result_and_the_edge_takes_the_edge_on_the_retry(self):
        self.register()
        real = lifecycle.auto_transition

        def dies(db, eid, to, *a, **k):
            if to != "SCREENING":
                raise RuntimeError("the worker died after the result")
            return real(db, eid, to, *a, **k)
        with mock.patch.object(lifecycle, "auto_transition", dies):
            with self.assertRaises(RuntimeError):
                self.screened(F, sharpe=1.5)
        self.assertEqual((lifecycle.state(self.db, F), self.results()), ("SCREENING", 1))
        again = pipeline.step_report(self.db, {"exp_id": F}, "report-1")
        self.assertEqual((again["state"], again.get("resumed"), self.results()), ("OBSERVATION", True, 1))
        self.assertEqual(lifecycle.state(self.db, F), "OBSERVATION")

    def test_a_lost_lease_on_the_report_job_never_stops_the_family(self):
        self.register()
        with mock.patch.object(pipeline, "step_report", lambda *a, **k: None):
            self.screened(F, sharpe=1.5)                       # the frozen artifacts; the report runs as a job below
        jid = f"report|{F}"
        agent = [a for a in fleet.agents(self.db_path) if a.name == "report-1"][0]

        def run():
            with self.db.tx():
                self.db.con.execute("UPDATE jobs SET status='queued', next_run=0, lease_owner=NULL WHERE job_id=?",
                                    (jid,))
            agent(self.db)
            return jobs.get(self.db, jid)
        with mock.patch.object(jobs, "complete", lambda *a, **k: False):    # the lease was lost: result discarded
            run()
        self.assertEqual((lifecycle.state(self.db, F), self.results()), ("OBSERVATION", 1))
        j = run()
        self.assertEqual(j["status"], "done", j["error"])
        self.assertTrue(j["result"]["resumed"])
        self.assertEqual(self.results(), 1)
        self.assertEqual(families.failed_jobs(self.db, BASE), [])



class ConfirmRechecksInsideItsTransaction(A3Base):
    """Review of 4c32ff6, finding 3: confirm checks W0, the per-tag limits and the programme stop again inside the
    write transaction (BEGIN IMMEDIATE) that writes the reservation, so two families confirmed at the same time cannot
    both pass. The other confirm is simulated as committing right after this one's first check."""

    def race(self, other):
        families.discover_all(self.db)
        self.revive()
        code = families.request(self.db, "fcarry", "human:anton", "Anton approves F1 after reading it")
        real = families._blocking_problems

        def then_the_other_commits(db, fam):
            bad = real(db, fam)
            other()
            return bad
        with mock.patch.object(families, "_blocking_problems", then_the_other_commits):
            with self.assertRaises(families.FamilyError) as c:
                families.confirm(self.db, code, "abcdef01", "human:anton")
        self.assertNotIn("fcarry", [e.get("family") for e in self.events("family.approved")])
        self.assertAlmostEqual(families.reserved(self.db, "fcarry"), 0.0)
        return str(c.exception)

    def test_w0(self):
        def other():
            for fid in ("fa", "fb", "fc", "fd"):
                self.db.append("alpha_ledger", exp_id=f"family:{fid}", ts=0, alpha=0.0125, note="A8 reserve")
        self.assertIn("alpha budget", self.race(other))

    def test_one_open_family_per_tag(self):
        def other():
            self.db.append("experiments", exp_id="E_ftwo__x1_a8", version=1, created_ts=0,
                           mechanism_tag="delta_neutral_funding_carry", fingerprint="E_ftwo__x1_a8",
                           spec_json={"execution": "taker", "family": "ftwo"})
            self.db.event("family.approved", "human:anton", None, {"family": "ftwo"})
        self.assertIn("at most 1 open family per tag", self.race(other))

    def test_the_programme_stop(self):
        def other():
            for fid in ("fa", "fb", "fc"):
                self.db.event("family.closed", "system:fixture", None, {"family": fid, "outcome": "FUTILE_IN_SAMPLE"})
        self.assertIn("programme stopped", self.race(other))



class EveryGateEdgeOfAFamilyNeedsItsStep(A3Base):
    """Review of 4c32ff6, finding 2: 'lab transition E VALIDATED --result-id <a forward PASS>' skipped the sealed holdout
    (VALIDATION -> VALIDATED is an automatic edge and the forward PASS is system-recorded). VALIDATION -> VALIDATED /
    REJECTED now need the holdout step's 'PASS (holdout)' / 'FAIL (holdout)' result citing its hash-matching
    holdout.json, and `lab transition` refuses a family instance on any edge outside registry.GATE_EDGES."""

    def cli(self, *args):
        out = []
        with mock.patch.dict(os.environ, {"CLAUDECODE": "1"}):
            main(list(args), db_path=self.db_path, out=out.append)
        return out

    def in_validation(self, e):
        for st in ("SCREENING", "OBSERVATION", "SCREEN_PASSED", "VALIDATION"):
            self.db.append("transitions", exp_id=e, ts=0, from_state=None, to_state=st, actor="fixture",
                           reason="fixture: the path to a holdout")

    def test_a_forward_pass_or_an_uncited_holdout_result_never_validates(self):
        self.ready()
        fleet.strategy_pass(self.db)
        self.in_validation(F)
        fwd = registry.record_result(self.db, F, "VALIDATION", families.FORWARD_PASS + ": fixture", {}, {},
                                     "system:validation-1")
        bare = registry.record_result(self.db, F, "VALIDATION", "PASS (holdout): no artifact", {}, {},
                                      "system:validation-1")
        for rid in (fwd, bare):
            out = self.cli("transition", F, "VALIDATED", "--reason", "skip the sealed holdout", "--result-id", str(rid))
            self.assertTrue(out and out[0].startswith("refused"), out)
        self.assertEqual(lifecycle.state(self.db, F), "VALIDATION")

    def test_the_holdout_steps_own_results_still_take_both_edges(self):
        self.ready()
        fleet.strategy_pass(self.db)
        for e, verdict, to in ((F, "PASS (holdout): fixture", "VALIDATED"), (L, "FAIL (holdout): fixture", "REJECTED")):
            self.in_validation(e)
            art = pipeline.save_artifact(e, "holdout", {"gates": {}})
            rid = registry.record_result(self.db, e, "VALIDATION", verdict, {}, {"artifacts": [art]},
                                         "system:validation-1")
            ev = {"result_id": rid}
            lifecycle.auto_transition(self.db, e, to, "system:validation-1", verdict, ev,
                                      guards=(registry.make_result_guard(ev),))
            self.assertEqual(lifecycle.state(self.db, e), to)

    def test_lab_transition_refuses_a_family_instance_on_any_non_gate_edge(self):
        families.discover_all(self.db)
        self.revive()
        out = self.cli("transition", F, "SUPPRESSED", "--reason", "withdraw it by hand")
        self.assertTrue(out and out[0].startswith("refused"), out)
        self.assertEqual(lifecycle.state(self.db, F), "DISCOVERED")
        self.approve()
        self.touch()
        fleet.strategy_pass(self.db)
        out = self.cli("transition", F, "SCREENING", "--reason", "start the screen by hand")
        self.assertTrue(out and out[0].startswith("refused"), out)
        self.assertEqual(lifecycle.state(self.db, F), "REGISTERED")



class SuccessorsAreFixedAtTheApproval(A5Base):
    """Review of 4c32ff6, finding 1 (points 5, 6 and 9): after approve-family no instance of the family is revived or
    withdrawn by hand, and a successor registers only if it was DISCOVERED when the approval was requested (the
    approval names it). Otherwise a human could revive filt_w once filt's frozen cost.json met the trigger, and cohort
    membership would be a choice made after the in-sample results were known."""
    GUARDS = (registry.complete_spec_guard, families.terminal_guard)

    def test_a_successor_revived_after_approve_family_never_joins_the_cohort(self):
        families.discover_all(self.db)
        self.revive(BASE)
        early = lifecycle.request_approval(self.db, S, "DISCOVERED", "human:anton", WHY)   # issued before the approval
        self.approve()
        self.touch()
        self.assertEqual(sorted(fleet.strategy_pass(self.db)["registered"]), BASE)
        self.screened(F, early=True, funding=-0.005)                          # filt rejected at train: triggered
        with self.assertRaises(lifecycle.LifecycleError):
            lifecycle.request_approval(self.db, S, "DISCOVERED", "human:anton", WHY, guards=self.GUARDS)
        with self.assertRaises(lifecycle.LifecycleError):
            lifecycle.confirm(self.db, early, "human:anton", guards=self.GUARDS)
        self.assertEqual(lifecycle.state(self.db, S), "SUPPRESSED")
        for e in (L, H):
            self.screened(e)
        self.assertEqual(fleet.strategy_pass(self.db)["registered"], [])
        self.assertTrue(self.status().startswith("forward test"))
        self.assertNotIn(S, families.cohort(self.db, "fcarry")["members"])
        self.assertEqual(lifecycle.state(self.db, S), "SUPPRESSED")

    def test_a_successor_revived_between_request_and_confirm_needs_a_new_code(self):
        """Review of fdd898a (end-to-end #1): the confirm is refused, so the successor is not dropped silently; a new
        approve-family names it."""
        families.discover_all(self.db)
        self.revive(BASE)
        code = families.request(self.db, "fcarry", "human:anton", "Anton approves F1 after reading it")
        self.revive([S])                                                      # after the request, before the confirm
        with self.assertRaises(families.FamilyError) as c:
            families.confirm(self.db, code, "abcdef01", "human:anton")
        self.assertIn("run approve-family again", str(c.exception))
        self.assertIsNone(families.approval(self.db, "fcarry"))
        self.assertAlmostEqual(families.reserved(self.db, "fcarry"), 0.0)
        self.approve()
        self.assertEqual(families.approval_payload(self.db, "fcarry")["successors"], [S])
        self.touch()
        self.assertEqual(sorted(fleet.strategy_pass(self.db)["registered"]), BASE)
        self.screened(F, early=True, funding=-0.005)
        self.assertEqual(fleet.strategy_pass(self.db)["registered"], [S])

    def test_a_successor_still_suppressed_at_approval_is_shown_and_recorded_as_dropped(self):
        families.discover_all(self.db)
        self.revive(BASE)
        summary = families.approval_summary(self.db, families.load("fcarry"))
        self.assertTrue(any(line.startswith(f"{S}: SUPPRESSED") and "DROPPED" in line for line in summary), summary)
        self.assertTrue(all("active" in line for line in summary if not line.startswith(S)), summary)
        self.approve()
        p = families.approval_payload(self.db, "fcarry")
        self.assertEqual((p["successors"], p["dropped_successors"]), ([], [S]))

    def test_a_successor_revived_before_the_request_is_named_by_the_approval(self):
        self.ready()
        self.assertEqual(families.approval_payload(self.db, "fcarry")["successors"], [S])

    def test_no_instance_is_withdrawn_by_hand_after_the_approval(self):
        self.ready()
        for e in (S, F):
            with self.assertRaises(lifecycle.LifecycleError):
                lifecycle.request_approval(self.db, e, "WITHDRAWN", "human:anton", "withdraw it now", guards=self.GUARDS)
            self.assertEqual(lifecycle.state(self.db, e), "DISCOVERED")



# ---------- review of fdd898a: three adversarial verifiers (protocol-statistics, engineering, end-to-end) ----------
_REAL_FETCH = data._fetch                          # A3Base replaces it with one that refuses every fetch


def _outage(error):
    """data._fetch during an outage: a cached file is reused, anything else raises `error(url)`."""
    def fetch(url, path, get=None):
        if os.path.exists(path):
            return path
        raise error(url)
    return fetch


def _cli(db_path, *argv):
    out = []
    rc = main(list(argv), db_path=db_path, out=out.append)
    return rc, "\n".join(map(str, out))


def _assistant_env():
    clean = {k: v for k, v in os.environ.items() if k != "CLAUDECODE" and not k.startswith("CLAUDE_CODE_")}
    return {**clean, "CLAUDECODE": "1"}


class MembershipIsTheInstanceId(A3Base):
    """Review of fdd898a, protocol #1: family membership is an amendment 8 instance id, never a name prefix. An id
    that starts like a family instance cannot be created, and one written past that guard is neither a member (no
    cohort, no 'registration started') nor exempt from the covering rule of point 7."""

    def test_an_id_that_looks_like_a_family_instance_is_reserved(self):
        for e in ("E_fcarry__x", "e_FCARRY__y", "E_other__thing"):
            self.assertTrue(families.reserved_id(e), e)
        for e in ("E_mvrv_value_p3", "E_day_of_week_p2", "E_tsmom_v1"):
            self.assertFalse(families.reserved_id(e), e)
        rc, text = _cli(self.db_path, "discover", "E_fcarry__x", "--hypothesis", "h", "--mechanism", "m",
                        "--instrument", "i", "--horizon", "days", "--execution", "taker", "--source", "s")
        self.assertTrue(text.startswith("refused"), text)

    def test_a_prefix_id_written_past_the_guard_is_no_member_and_still_covers(self):
        families.discover_all(self.db)
        self.revive()
        Y = "E_fcarry__y"
        self.db.append("experiments", exp_id=Y, version=1, created_ts=0, mechanism_tag="delta_neutral_funding_carry",
                       fingerprint=Y, spec_json={"execution": "taker"})
        self.db.append("transitions", exp_id=Y, ts=0, from_state=None, to_state="REGISTERED", actor="human:anton",
                       reason="fixture: an ordinary experiment written past the reserved-id guard")
        self.assertNotIn(Y, families.members(self.db, "fcarry"))
        self.assertFalse(families.registration_started(self.db, "fcarry"))
        self.approve()                                       # not 'already registered' (PoC P5b)
        self.touch()
        block = families.registration_block(self.db, families.load("fcarry"))
        self.assertTrue(any("open experiment(s) outside the family" in b and Y in b for b in block), block)
        self.assertEqual(fleet.strategy_pass(self.db)["registered"], [])


class TheCohortWaitsForTheScreensEdge(A5Base):
    """Review of fdd898a, protocol #2: a member whose report recorded its result but has not taken its edge yet (a
    crash between the two, or a strategy pass in between) is not settled: the cohort waits for the retry, so M and
    alpha_i are never computed without a survivor."""

    def test_a_crash_between_the_result_and_the_edge_holds_the_cohort(self):
        self.register()
        real = lifecycle.auto_transition

        def crash(db, eid, to, *a, **k):
            if to == "OBSERVATION" and eid == F:
                raise RuntimeError("the fleet died between the result and the edge")
            return real(db, eid, to, *a, **k)
        with mock.patch.object(lifecycle, "auto_transition", crash):
            with self.assertRaises(RuntimeError):
                self.screened(F, sharpe=3.0)                  # the best survivor
        self.screened(L, sharpe=2.0)
        self.screened(H, sharpe=1.0)
        self.assertEqual(self.status(), "screening: 2 of 3 registered members have a result")
        self.assertIsNone(families.cohort(self.db, "fcarry"))
        pipeline.step_report(self.db, {"exp_id": F}, "report-1")         # the retry takes the edge
        self.assertTrue(self.status().startswith("forward test"))
        cf = families.cohort(self.db, "fcarry")
        self.assertEqual((cf["M"], sorted(cf["selected"])), (3, sorted(BASE)))


class TheProgrammeStopLatches(A3Base):
    """Review of fdd898a, protocol #3 (point 15: only a new dated amendment restarts the programme)."""

    def closed(self, fid, outcome):
        self.db.event("family.closed", "system:strategy-1", None, {"family": fid, "outcome": outcome})

    def counted_pass(self, fid, ts_):
        e = f"E_{fid}__x1_a8"
        self.db.append("experiments", exp_id=e, version=1, created_ts=0, mechanism_tag="t", fingerprint=e,
                       spec_json={"family": fid})
        self.db.append("results", exp_id=e, version=1, ts=ts_, label="VALIDATION",
                       verdict=families.FORWARD_PASS + ": fixture", metrics={}, evidence={}, supersedes=None)

    def test_three_closes_without_a_pass_stop_it_for_good(self):
        for f in ("aaa", "bbb", "ccc"):
            self.closed(f, "FUTILE_IN_SAMPLE")
        self.assertTrue(families.programme_stop(self.db))
        self.closed("ddd", "PASS")                           # an outcome field alone never counts
        self.assertTrue(families.programme_stop(self.db))
        with mock.patch.object(families, "forward_result", lambda db, e, r: "PASS"):
            self.counted_pass("ddd", 0)                       # even a counted PASS of a later close
            self.assertIn("family:ddd", families.forward_passes(self.db))
            self.assertTrue(families.programme_stop(self.db))
            self.assertTrue(families._programme_limits(self.db, FCARRY))

    def test_a_pass_recorded_after_2028_06_30_never_lifts_the_stop(self):
        late = ts(2028, 9, 10)
        with mock.patch.object(families, "forward_result", lambda db, e, r: "PASS"):
            self.counted_pass("eee", late)
            self.assertIn("family:eee", families.forward_passes(self.db))
            self.assertTrue(families.programme_stop(self.db, late))
            self.counted_pass("fff", ts(2028, 6, 30, 12))
            self.assertEqual(families.programme_stop(self.db, late), [])


class NoHumanMembershipChangeAfterTheApproval(A5Base):
    """Review of fdd898a, protocol #4 and #5: a registered member is never withdrawn by hand, and `lab transition`
    never rejects a screen survivor on its OBSERVE result (SCREENING -> REJECTED needs the screen's REJECTED result)."""
    GUARDS = (registry.complete_spec_guard, families.terminal_guard)

    def test_a_registered_member_is_never_withdrawn(self):
        self.register()
        for e in BASE:
            with self.assertRaises(lifecycle.LifecycleError):
                lifecycle.request_approval(self.db, e, "WITHDRAWN", "human:anton", "withdraw it now",
                                           guards=self.GUARDS)
            self.assertEqual(lifecycle.state(self.db, e), "REGISTERED")

    def test_lab_transition_never_rejects_a_survivor_on_its_observe_result(self):
        self.register()
        real = lifecycle.auto_transition

        def crash(db, eid, to, *a, **k):
            if to == "OBSERVATION":
                raise RuntimeError("the fleet died between the result and the edge")
            return real(db, eid, to, *a, **k)
        with mock.patch.object(lifecycle, "auto_transition", crash):
            with self.assertRaises(RuntimeError):
                self.screened(F, sharpe=3.0)
        rid = self.db.one("SELECT id FROM results WHERE exp_id=? ORDER BY id DESC", F)[0]
        with mock.patch.dict(os.environ, _assistant_env(), clear=True):
            rc, text = _cli(self.db_path, "transition", F, "REJECTED", "--result-id", str(rid), "--reason",
                            "pick who survives")
        self.assertEqual(rc, 1, text)
        self.assertIn("SCREENING -> REJECTED needs the screen's own 'REJECTED' result", text)
        self.assertEqual(lifecycle.state(self.db, F), "SCREENING")


class RevokeIsAHumanTerminalStepInsideItsTransaction(A3Base):
    """Review of fdd898a, protocol #6 and #7, engineering #3: revoke-family needs the terminal guard, and its checks run
    inside the transaction that writes, so two revokes, or a revoke and the registration, cannot both pass."""

    def test_an_assistant_session_cannot_revoke(self):
        self.ready()
        self.p[0].stop()                                     # the real guard
        try:
            with mock.patch.dict(os.environ, _assistant_env(), clear=True):
                rc, text = _cli(self.db_path, "revoke-family", "fcarry", "--reason", "an assistant revokes it")
        finally:
            self.p[0].start()
        self.assertEqual(rc, 1, text)
        self.assertIsNotNone(families.approval(self.db, "fcarry"))
        self.assertAlmostEqual(families.alpha_reserved(self.db), 0.0125)

    def test_two_revokes_at_once_release_alpha_f_once(self):
        self.ready()
        other, real_tx, fired = DB(self.db_path), self.db.tx, []

        def tx():
            if not fired:
                fired.append(1)
                families.revoke(other, "fcarry", "human:anton", "the second terminal revokes too")
            return real_tx()
        with mock.patch.object(self.db, "tx", tx):
            families.revoke(self.db, "fcarry", "human:anton", "the first terminal revokes")
        other.close()
        self.assertAlmostEqual(families.reserved(self.db, "fcarry"), 0.0)
        self.assertAlmostEqual(families.alpha_reserved(self.db), 0.0)

    def test_a_revoke_racing_the_registration_is_refused(self):
        self.ready()
        real_tx, fired = self.db.tx, []

        def tx():
            if not fired:                                    # the fleet registers between the check and the write
                fired.append(1)
                self.db.append("transitions", exp_id=F, ts=0, from_state="DISCOVERED", to_state="REGISTERED",
                               actor="system:strategy-1", reason="fixture: the registration got there first")
            return real_tx()
        with mock.patch.object(self.db, "tx", tx):
            with self.assertRaises(families.FamilyError):
                families.revoke(self.db, "fcarry", "human:anton", "revoke while the batch registers")
        self.assertAlmostEqual(families.reserved(self.db, "fcarry"), 0.0125)


class FamilyFileRulesAreExact(unittest.TestCase):
    """Review of fdd898a, protocol #8 and #9: alpha_F is exactly 0.0125 (point 13) and every lookback in a grid is
    within max_lookback_days <= 14 (point 3)."""

    def test_alpha_f_is_exactly_0_0125(self):
        for a in (0.005, 0.008, 0.01, 0.0124):
            self.assertTrue(any("alpha.family" in p for p in problems_of(alpha__family=a)), a)
        self.assertEqual(problems_of(), [])

    def test_every_grid_lookback_is_within_14_days(self):
        g = [{"lookback_days": 60, "enter_apr": 0.1}, {"lookback_days": 7, "enter_apr": 0.2}]
        self.assertTrue(any("lookback" in p for p in problems_of(instances__0__grid=g)))
        f = [{"days": 14, "q": 0.8}, {"days": 90, "q": 0.95}]
        self.assertTrue(any("days=90" in p for p in problems_of(instances__2__grid=f)))
        h = [{"lookback_days": 8, "exit_apr": 0.0}, {"lookback_days": 7, "exit_apr": 0.1}]   # above its own 7
        self.assertTrue(any("lookback_days=8" in p for p in problems_of(instances__1__grid=h)))


class ADownloadFailureNeverStopsAFamily(A3Base):
    """Review of fdd898a, engineering #1: a family download that fails (network, 5xx, 429) defers the job by an hour
    without using an attempt and records why; it never fails the job for good and stops the family."""

    def test_the_data_job_waits_and_retries(self):
        self.now[0] = ts(2026, 10, 20)
        self.queue_on_the_fixture_clock()
        self.ready(files=False)
        self.touch(kinds=("klines", "funding"))
        self.assertEqual(sorted(fleet.strategy_pass(self.db)["registered"]), BASE)
        agent = [a for a in fleet.agents(self.db_path) if a.name == "data-1"][0]

        with mock.patch.object(data, "_fetch", _outage(lambda url: IOError(f"download failed: {url}"))), \
                mock.patch.object(pipeline.time, "time", lambda: self.now[0]):
            for _ in BASE:
                agent(self.db)
        for e in BASE:
            j = jobs.get(self.db, f"data|{e}")
            self.assertEqual((j["status"], j["attempts"], j["next_run"]),
                             ("queued", 0, self.now[0] + pipeline.DOWNLOAD_RETRY_S), e)
        self.assertEqual(self.db.one("SELECT COUNT(*) FROM events WHERE kind='job.failed'")[0], 0)
        self.assertTrue(any("retries in 60 minutes" in r for w in self.events("family.waiting") for r in w["reasons"]))
        self.assertFalse(fleet.strategy_pass(self.db)["families"]["fcarry"].startswith("stopped"))

    def test_any_other_error_still_fails_as_before(self):
        self.now[0] = ts(2026, 10, 20)
        self.ready(files=False)
        self.touch(kinds=("klines", "funding"))
        fleet.strategy_pass(self.db)
        spec = pipeline._spec(self.db, F)
        with mock.patch.object(data, "_fetch", _outage(lambda url: OSError("disk full"))):
            with self.assertRaises(OSError):
                pipeline._download(self.db, F, spec, "train3", "data-1", ["BTCUSDT"])


class TheDownloadLimitHoldsAcrossProcesses(A3Base):
    """Review of fdd898a, engineering #4: the 2 download slots of amendment 9 are lock files shared by every process
    (heavy workers are separate processes); and two writers of one file never share a .part file."""

    def test_a_third_download_waits_for_a_slot(self):
        import fcntl
        import threading
        d = os.path.join(self.cache, ".download_slots")
        os.makedirs(d, exist_ok=True)
        held = [open(os.path.join(d, f"slot{i}.lock"), "a+") for i in range(2)]
        for f in held:                                       # another process holds both slots
            fcntl.flock(f, fcntl.LOCK_EX)
        calls = []
        get = families.guarded_get("train3", fetch=lambda url: calls.append(url) or b"zip")
        url = f"{data.SPOT_BASE}/klines/BTCUSDT/1h/BTCUSDT-1h-2023-01.zip"
        self.now[0] = ts(2026, 10, 20)
        t = threading.Thread(target=get, args=(url,))
        t.start()
        t.join(0.6)
        self.assertEqual(calls, [])                          # waiting for a slot
        fcntl.flock(held[0], fcntl.LOCK_UN)
        t.join(5)
        self.assertEqual(calls, [url])
        for f in held:
            f.close()

    def test_two_writers_never_share_a_part_file(self):
        seen = []
        real = os.replace
        with mock.patch.object(data.os, "replace", lambda a, b: seen.append(a) or real(a, b)):
            p = _REAL_FETCH("https://example.invalid/x.zip", os.path.join(self.cache, "x", "x.zip"),
                            get=lambda url: b"zip")
        self.assertTrue(os.path.exists(p))
        self.assertIn(f".{os.getpid()}.", seen[0])


class SuccessorsKeepTheApprovalTheRegistrationCited(A5Base):
    """Review of fdd898a, engineering #2: once the base batch is registered, a change to a bound file the steps do not
    pin (the adapter, the vocabulary, a gate value) no longer drops a named successor or fixes the cohort early: what
    registers is bound by the approval the registration cited. A changed family file or module still fails closed."""

    def test_an_adapter_change_after_registration_keeps_the_successor(self):
        self.register()
        self.blobs["adapter"] = {**self.blobs["adapter"], "committed": "9999", "working": "9999"}
        self.assertIsNone(families.approval(self.db, "fcarry"))               # void for a new registration
        self.screened(F, early=True, funding=-0.005)                          # filt rejected at train: triggered
        self.assertEqual(fleet.strategy_pass(self.db)["registered"], [S])
        for e in (L, H):
            self.screened(e)
        self.screened(S, sharpe=0.5)
        self.assertTrue(self.status().startswith("forward test"))
        self.assertIn(S, families.cohort(self.db, "fcarry")["members"])

    def test_a_changed_family_file_after_registration_fails_closed(self):
        self.register()
        self.screened(F, early=True, funding=-0.005)                          # triggered
        self.blobs["family"] = {**self.blobs["family"], "committed": "abcdef01ffff", "working": "abcdef01ffff"}
        self.assertIsNone(families.binding_approval(self.db, "fcarry"))
        self.assertEqual(fleet.strategy_pass(self.db)["registered"], [])
        self.assertEqual(lifecycle.state(self.db, S), "DISCOVERED")


class TheHumanTextsAndSmallGuards(A5Base):
    """Review of fdd898a, end-to-end #3-#6 and protocol #10: python3 in the printed commands, the family's own members
    are no graveyard hit, shadow-start refuses a family instance, and the dashboard's screening alpha leaves out the
    amendment 8 rows."""

    def test_the_printed_confirm_command_runs_on_this_pc(self):
        families.discover_all(self.db)
        rc, text = _cli(self.db_path, "approve", F, "DISCOVERED", "--reason", WHY)
        self.assertEqual(rc, 0, text)
        self.assertIn("python3 -m lab confirm ", text)

    def test_the_familys_own_members_are_no_graveyard_hit(self):
        self.register()
        self.screened(F, observe=False)
        self.assertEqual(lifecycle.state(self.db, F), "REJECTED")
        hits, unacked = families.graveyard_hits(self.db, families.load("fcarry"))
        self.assertNotIn(F, hits)
        self.assertNotIn(F, unacked)

    def test_shadow_start_refuses_a_family_instance(self):
        self.register()
        self.screened(F, sharpe=1.5)
        self.assertEqual(lifecycle.state(self.db, F), "OBSERVATION")
        rc, text = _cli(self.db_path, "shadow-start", F, "--reason", "shadow trade the family member")
        self.assertEqual(rc, 1, text)
        self.assertIn(families.NO_PAPER, text)
        self.assertEqual(self.db.one("SELECT COUNT(*) FROM events WHERE kind='shadow.approved'")[0], 0)

    def test_the_card_shows_danish_waiting_reasons_and_the_instance_states(self):
        self.now[0] = ts(2026, 10, 25)                                      # the embargo: registration waits
        self.ready(files=False)
        self.assertEqual(fleet.strategy_pass(self.db)["registered"], [])
        row = next(r for r in command.families_card(self.db, self.now[0])["families"] if r["family"] == "fcarry")
        self.assertTrue(row["waiting"]["current"])
        self.assertTrue(row["waiting"]["reasons_da"][0].startswith("filer mangler og må først hentes fra 2026-11-28"),
                        row["waiting"])
        self.assertIn("may not be downloaded before 2026-11-28", row["waiting"]["reasons"][0])   # the registry text
        self.assertEqual(row["members"], {"DISCOVERED": 4})
        self.assertEqual(command.reason_da("something new"), "something new")                 # unknown: as recorded

    def test_a_registered_family_shows_the_approval_its_registration_cited(self):
        self.register()
        self.blobs["adapter"] = {**self.blobs["adapter"], "committed": "9999", "working": "9999"}  # a later deploy
        self.assertIsNone(families.approval(self.db, "fcarry"))
        state, ev = command._family_approval(self.db, "fcarry", self.now[0] + 10 ** 6)
        self.assertEqual(state, "approved")
        rc, text = _cli(self.db_path, "families")
        self.assertIn("fcarry: approved (event", text)
        self.blobs["module"] = {**self.blobs["module"], "committed": "8888", "working": "8888"}   # point 18
        state, _ = command._family_approval(self.db, "fcarry", self.now[0] + 2 * 10 ** 6)
        self.assertIn("fails closed", state)

    def test_the_dashboard_screening_alpha_leaves_out_amendment_8_rows(self):
        from lab import web
        before = web.overview(self.db)["alpha_spent"]
        self.register()
        self.assertAlmostEqual(families.alpha_reserved(self.db), 0.0125)
        self.assertAlmostEqual(web.overview(self.db)["alpha_spent"], before)


if __name__ == "__main__":
    unittest.main()
