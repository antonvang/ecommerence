"""Director order 52 P1: synthetic November-14 readiness checks (research/tools/nov14_readiness.py on
research/desk/GATE_MATRIX.json). Simulated clocks and flags only; no network (socket patched), nothing written."""
import copy
import datetime as dt
import io
import json
import os
import shutil
import socket
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "research", "tools"))
import nov14_readiness as nr  # noqa: E402

A_FLAGS = {"owner_confirms_lock_A", "lock_A_committed"}
B_FLAGS = {"owner_confirms_lock_B", "owner_resolves_B_point1", "lock_B_committed"}
F2_FLAGS = {"owner_ack_f2_calibration", "f2_calibration_spec_committed"}


def _no_net(*a, **k):
    raise AssertionError("network used")


class NoNetwork(unittest.TestCase):
    def setUp(self):
        patches = [mock.patch.object(socket, "socket", _no_net), mock.patch.object(socket, "create_connection", _no_net),
                   mock.patch.object(socket, "getaddrinfo", _no_net)]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.m = nr.load()


class Matrix(NoNetwork):
    def test_matrix_is_valid_and_no_gate_opens_early(self):
        self.assertEqual(nr.validate(self.m), [])

    def test_floors(self):
        g = nr.gate_index(self.m)
        self.assertEqual(g["G01_HIST_1114"]["earliest_utc"], "2026-11-14T00:00:00Z")
        self.assertEqual(g["G09_COINM_1128"]["earliest_utc"], "2026-11-28T00:00:00Z")
        self.assertEqual(g["G11_RESTART_1128"]["earliest_utc"], "2026-11-28T00:00:00Z")
        self.assertGreaterEqual(nr.gate_earliest(g["G01_HIST_1114"]), nr.tool_earliest("research/tools/n6_funding.py"))
        self.assertGreaterEqual(nr.gate_earliest(g["G01_HIST_1114"]), nr.tool_earliest("research/tools/n4_kimchi.py"))

    def test_every_gate_has_a_rule_source(self):
        for g in self.m["gates"]:
            self.assertTrue(g["source"], g["id"])
            for s in g["source"]:
                self.assertTrue(os.path.exists(os.path.join(HERE, s["file"])), (g["id"], s["file"]))

    def test_early_gate_is_detected(self):
        bad = copy.deepcopy(self.m)
        for g in bad["gates"]:
            if g["id"] == "G09_COINM_1128":
                g["earliest_utc"] = "2026-11-20T00:00:00Z"
        errs = nr.validate(bad)
        self.assertTrue(any("G09_COINM_1128 opens before its floor" in e for e in errs), errs)

    def test_status_mismatch_is_detected(self):
        bad = copy.deepcopy(self.m)
        for g in bad["gates"]:
            if g["id"] == "G01_HIST_1114":
                g["status_at_as_of"] = "OPEN"
        self.assertTrue(any("G01_HIST_1114: status_at_as_of" in e for e in nr.validate(bad)))

    def test_unknown_gate_in_action_is_invalid_and_blocks(self):
        bad = copy.deepcopy(self.m)
        for a in bad["actions"]:
            if a["id"] == "hfc1_report_3d":
                a["gates"].append("G99_NOT_THERE")
        self.assertTrue(any("unknown gate G99_NOT_THERE" in e for e in nr.validate(bad)))
        ok, why = nr.decide(bad, "hfc1_report_3d", "2026-11-09T00:00:00Z", "HFC1")
        self.assertFalse(ok)
        self.assertIn("UNKNOWN_GATE: G99_NOT_THERE", why)


class Decisions(NoNetwork):
    def d(self, action, now, study=None, flags=()):
        return nr.decide(self.m, action, now, study, flags)

    def test_historical_fetch_blocked_before_1114_even_with_all_flags(self):
        every = A_FLAGS | B_FLAGS | F2_FLAGS
        for study in ("A_n6", "B_n4", "F2"):
            for now in ("2026-11-06T14:38:27Z", "2026-11-13T23:59:59Z"):
                ok, why = self.d("historical_fetch", now, study, every)
                self.assertFalse(ok, (study, now))
                self.assertTrue(any(r.startswith("NOT_YET: G01_HIST_1114") for r in why), why)

    def test_historical_fetch_at_1114_only_listed_studies_with_their_flags(self):
        t = "2026-11-14T00:00:00Z"
        self.assertTrue(self.d("historical_fetch", t, "A_n6", A_FLAGS)[0])
        self.assertTrue(self.d("historical_fetch", t, "B_n4", B_FLAGS)[0])
        self.assertTrue(self.d("historical_fetch", t, "F2", F2_FLAGS)[0])
        for study, flags in (("A_n6", A_FLAGS), ("B_n4", B_FLAGS), ("F2", F2_FLAGS)):
            self.assertFalse(self.d("historical_fetch", t, study)[0], study)
            for drop in flags:                                  # every single listed flag is necessary
                ok, why = self.d("historical_fetch", t, study, flags - {drop})
                self.assertFalse(ok, (study, drop))
                self.assertTrue(any(r.startswith("MISSING_FLAGS") and drop in r for r in why), why)
        every = A_FLAGS | B_FLAGS | F2_FLAGS
        for study in ("C1", "F3", "HFC1", "STRAKS", "PAIRS", "S1", "LIQPROXY1", "UNKNOWN_STUDY", None):
            self.assertFalse(self.d("historical_fetch", t, study, every)[0], study)
        self.assertFalse(self.d("historical_fetch", t, "A_n6", B_FLAGS)[0])     # another study's flags do not help

    def test_f2_confirmation_window_stays_blocked_without_signature(self):
        ok, why = self.d("historical_fetch_train3_validation3", "2026-11-20T00:00:00Z", "F2", F2_FLAGS)
        self.assertFalse(ok)
        self.assertTrue(any("G15_OWNER_SIGNATURE" in r for r in why))

    def test_upbit_only_b_after_its_lock(self):
        self.assertFalse(self.d("upbit_fetch", "2026-11-13T23:59:59Z", "B_n4", B_FLAGS)[0])
        self.assertTrue(self.d("upbit_fetch", "2026-11-14T00:00:00Z", "B_n4", B_FLAGS)[0])
        self.assertFalse(self.d("upbit_fetch", "2026-11-14T00:00:00Z", "B_n4",
                                B_FLAGS - {"lock_B_committed"})[0])
        self.assertFalse(self.d("upbit_fetch", "2026-11-14T00:00:00Z", "A_n6", A_FLAGS | B_FLAGS)[0])

    def test_coinm_blocked_until_1128(self):
        for now in ("2026-11-14T00:00:00Z", "2026-11-27T23:59:59Z"):
            ok, why = self.d("coinm_fetch", now, "A_n6_X3", A_FLAGS)
            self.assertFalse(ok)
            self.assertTrue(any(r.startswith("NOT_YET: G09_COINM_1128") for r in why), why)
            self.assertFalse(self.d("run_n6_x3", now, "A_n6_X3", A_FLAGS | {"loader_tests_green"})[0])
        self.assertTrue(self.d("coinm_fetch", "2026-11-28T00:00:00Z", "A_n6_X3", A_FLAGS)[0])
        self.assertFalse(self.d("coinm_fetch", "2026-11-28T00:00:00Z", "A_n6_X3", set())[0])
        ok, why = self.d("coinm_fetch", "2026-11-28T00:00:00Z", "F3", A_FLAGS)
        self.assertFalse(ok)                                    # F3 needs its own signed activation

    def test_restart_blocked_until_1127_inclusive(self):
        for now in ("2026-11-06T14:38:27Z", "2026-11-27T00:00:00Z", "2026-11-27T23:59:59Z"):
            for action in ("host_restart", "system_update"):
                ok, why = self.d(action, now, "OPS", {"owner_requests_restart"})
                self.assertFalse(ok, (action, now))
        self.assertTrue(self.d("host_restart", "2026-11-28T00:00:00Z", "OPS", {"owner_requests_restart"})[0])
        self.assertFalse(self.d("host_restart", "2026-11-28T00:00:00Z", "OPS")[0])

    def test_unknown_action_and_bad_time_are_blocked(self):
        for action in ("deploy_lab", "fetch_everything", "", None):
            ok, why = self.d(action, "2026-11-28T00:00:00Z", "A_n6", A_FLAGS)
            self.assertFalse(ok)
            self.assertTrue(why[0].startswith("UNKNOWN_ACTION"), why)
        for bad in ("2026-11-14 00:00:00", "2026-11-14T00:00:00+00:00", "soon", dt.datetime(2026, 11, 14), None,
                    True, {"t": 1}):
            ok, why = self.d("historical_fetch", bad, "A_n6", A_FLAGS)
            self.assertFalse(ok, bad)
            self.assertTrue(why[0].startswith("BAD_TIME"), why)
        aware = dt.datetime(2026, 11, 14, tzinfo=dt.timezone.utc)
        self.assertTrue(self.d("historical_fetch", aware, "A_n6", A_FLAGS)[0])

    def test_prohibited_actions_never_allowed(self):
        every = set()
        for g in self.m["gates"]:
            every |= set(g["required_flags"])
        for a in self.m["actions"]:
            for fl in a["studies"].values():
                every |= set(fl)
        for action in ("read_2024_holdout", "read_reserved_2025plus", "use_quarantined_file", "pm_lp_change",
                       "real_money_order", "s2_activate", "assistant_sign_or_approve"):
            for now in ("2026-11-14T00:00:00Z", "2026-11-28T00:00:00Z", "2030-01-01T00:00:00Z"):
                for study in (None, "A_n6", "F2", "OPS"):
                    self.assertFalse(self.d(action, now, study, every)[0], (action, now, study))

    def test_c1_cannot_activate_without_all_owner_flags(self):
        need = set(nr.action_index(self.m)["c1_activate"]["studies"]["C1"])
        self.assertFalse(self.d("c1_activate", "2026-11-13T23:59:59Z", "C1", need)[0])
        self.assertTrue(self.d("c1_activate", "2026-11-14T00:00:00Z", "C1", need)[0])
        for drop in need:
            self.assertFalse(self.d("c1_activate", "2026-11-14T00:00:00Z", "C1", need - {drop})[0], drop)

    def test_report_dates(self):
        cases = (("hfc1_report_3d", "HFC1", "2026-11-08T00:00:00Z"),
                 ("straks_report_7d", "STRAKS", "2026-11-12T17:01:51Z"),
                 ("pairs_report_diag", "PAIRS", "2026-11-19T20:41:09Z"),
                 ("s1_evaluate", "S1", "2026-11-20T09:55:07Z"))
        for action, study, t in cases:
            e = nr.parse_utc(t)
            self.assertFalse(self.d(action, e - 1, study)[0], action)
            self.assertTrue(self.d(action, e, study)[0], action)

    def test_alpha_charge_needs_ranking_that_includes_the_study(self):
        base = {"owner_key_registered", "owner_signed_alpha_ranking"}
        self.assertFalse(self.d("alpha_charge_w0", "2026-12-07T00:00:00Z", "F2", base)[0])
        self.assertTrue(self.d("alpha_charge_w0", "2026-12-07T00:00:00Z", "F2", base | {"w0_rank_includes_F2"})[0])
        self.assertFalse(self.d("alpha_charge_w0", "2026-12-07T00:00:00Z", "LIQPROXY1",
                                base | {"w0_rank_includes_F2"})[0])


class Hashes(NoNetwork):
    def test_listed_hashes_match_repo(self):
        self.assertEqual(nr.verify_hashes(self.m), [])

    def test_prefix_pinned_row_ignores_appended_notes_but_not_rule_edits(self):
        rows = [r for r in self.m["protocol_identities"] if r.get("prefix_bytes")]
        self.assertEqual([r["id"] for r in rows], ["HFC1_PROTOCOL"])
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp)
        r = rows[0]
        dst = os.path.join(tmp, r["path"])
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copyfile(os.path.join(HERE, r["path"]), dst)
        with open(dst, "a", encoding="utf-8") as fh:
            fh.write("\n- driftsnote (syntetisk)\n")
        self.assertEqual(nr.sha256_file(dst, r["prefix_bytes"]), r["sha256"])
        with open(dst, "r+b") as fh:
            fh.seek(100)
            b = fh.read(1)
            fh.seek(100)
            fh.write(bytes([b[0] ^ 1]))
        self.assertNotEqual(nr.sha256_file(dst, r["prefix_bytes"]), r["sha256"])
        self.assertEqual(nr.sha256_file(os.path.join(HERE, "research", "desk", "fomo", "__init__.py"), 10), "SHORT_FILE")

    def test_hash_mismatch_detected(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp)
        rows = self.m["protocol_identities"]
        for r in rows:
            dst = os.path.join(tmp, r["path"])
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copyfile(os.path.join(HERE, r["path"]), dst)
        self.assertEqual(nr.verify_hashes(self.m, root=tmp), [])
        target = os.path.join(tmp, "research", "PROTOCOL_V3.md")
        with open(target, "a", encoding="utf-8") as fh:
            fh.write("\n## Ændring 99 (syntetisk): metode n6\n")
        errs = nr.verify_hashes(self.m, root=tmp)
        self.assertTrue(any(e.startswith("HASH_MISMATCH research/PROTOCOL_V3.md") for e in errs), errs)
        os.remove(os.path.join(tmp, "lab", "pairs.py"))
        self.assertTrue(any(e == "MISSING lab/pairs.py" for e in nr.verify_hashes(self.m, root=tmp)))

    def test_readiness_table_must_equal_matrix(self):
        bad = copy.deepcopy(self.m)
        bad["protocol_identities"][0]["sha256"] = "0" * 64
        errs = nr.verify_hashes(bad)
        self.assertIn("NOV14_READINESS table and GATE_MATRIX protocol_identities differ", errs)
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp)
        md = os.path.join(tmp, "r.md")
        with open(md, "w", encoding="utf-8") as fh:
            fh.write("no table here\n")
        self.assertTrue(nr.verify_hashes(self.m, readiness_path=md)[0].startswith("readiness table"))


class ReadOnly(NoNetwork):
    def test_checker_writes_nothing_and_has_no_network_import(self):
        with open(os.path.join(HERE, "research", "tools", "nov14_readiness.py"), encoding="utf-8") as fh:
            src = fh.read()
        for bad in ("import socket", "urllib", "http.client", "requests", "sqlite3", "subprocess", "open(path, \"w",
                    "api.upbit.com"):
            self.assertNotIn(bad, src)
        before = {p: os.path.getmtime(os.path.join(HERE, p)) for p in
                  ("research/desk/GATE_MATRIX.json", "research/desk/NOV14_READINESS.md")}
        out = mock.patch("sys.stdout", new_callable=io.StringIO)
        with out:
            nr.main(["validate"])
            nr.main(["verify-hashes"])
            nr.main(["status", "--now", "2026-11-14T00:00:00Z"])
            nr.main(["check", "--now", "2026-11-14T00:00:00Z", "--action", "historical_fetch", "--study", "A_n6",
                     "--flag", "owner_confirms_lock_A", "--flag", "lock_A_committed"])
        after = {p: os.path.getmtime(os.path.join(HERE, p)) for p in before}
        self.assertEqual(before, after)

    def test_cli_exit_codes(self):
        with mock.patch("sys.stdout", new_callable=io.StringIO):
            self.assertEqual(nr.main(["check", "--now", "2026-11-13T00:00:00Z", "--action", "historical_fetch",
                                      "--study", "A_n6", "--flag", "owner_confirms_lock_A",
                                      "--flag", "lock_A_committed"]), 2)
            self.assertEqual(nr.main(["check", "--now", "2026-11-14T00:00:00Z", "--action", "historical_fetch",
                                      "--study", "A_n6", "--flag", "owner_confirms_lock_A",
                                      "--flag", "lock_A_committed"]), 0)
            self.assertEqual(nr.main(["validate"]), 0)

    def test_matrix_json_names_studies_consistently(self):
        st = set(self.m["studies"])
        for want in ("F2", "C1", "A_n6", "A_n6_X3", "B_n4", "HFC1", "STRAKS", "PAIRS", "S1", "F3", "OPS"):
            self.assertIn(want, st)
        json.dumps(self.m)


if __name__ == "__main__":
    unittest.main()
