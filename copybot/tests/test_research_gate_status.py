"""Director order 60 track B: read-only gate-status tool (research/tools/gate_status.py). Synthetic matrices and the
real GATE_MATRIX.json; simulated clocks; no network (socket and subprocess patched); nothing protected is written."""
import copy
import hashlib
import io
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "research", "tools"))
import gate_status as gs  # noqa: E402
import nov14_readiness as nr  # noqa: E402

BEFORE, AT, AFTER = "2026-11-13T23:59:59Z", "2026-11-14T00:00:00Z", "2026-11-14T00:30:00Z"
LATE = "2026-11-27T12:00:00Z"
PROTECTED = ("research/desk/GATE_MATRIX.json", "research/desk/NOV14_READINESS.md")


def _no_net(*a, **k):
    raise AssertionError("network used")


def _no_proc(*a, **k):
    raise AssertionError("subprocess used")


def _sha(rel):
    with open(os.path.join(HERE, rel), "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def synthetic_matrix():
    def g(gid, kind, earliest=None, flags=(), studies=("X",)):
        return {"id": gid, "kind": kind, "earliest_utc": earliest, "required_flags": list(flags),
                "studies": list(studies), "protects": "synthetic %s" % gid, "status_at_as_of": "CLOSED",
                "source": [{"file": "x", "loc": "y"}]}
    return {
        "version": "gate_matrix/1", "as_of_utc": "2026-11-09T00:00:00Z", "horizon_end_utc": "2026-11-28T23:59:59Z",
        "studies": {"X": "synthetic", "X_wd": "synthetic, withdrawn", "Y": "synthetic, no route"},
        "protocol_identities": [],
        "gates": [g("S_DATE", "date", AT), g("S_NEVER", "never"), g("S_CONSTRAINT", "constraint"),
                  g("S_OWNER", "date+owner", AT, ["owner_confirms_x"]),
                  g("S_WORK", "date+owner", AT, ["x_committed"]),
                  g("S_NODATE_OWNER", "owner", None, ["owner_key_x"]),
                  g("S_WD", "date+lock", AT, ["x_wd_committed"], ("X_wd",)),
                  g("S_LOCK", "date+lock", AT, [], ("X", "X_wd", "Y")),
                  g("S_BADKIND", "sometimes")],
        "actions": [{"id": "a_lock", "gates": ["S_LOCK"], "constraints": [],
                     "studies": {"X": ["owner_confirms_x", "x_committed"], "X_wd": ["owner_confirms_wd"]}},
                    {"id": "a_lock_more", "gates": ["S_LOCK", "S_DATE"], "constraints": [],
                     "studies": {"X": ["owner_confirms_x", "x_committed", "loader_ok"]}},
                    {"id": "a_wd", "gates": ["S_WD"], "constraints": [],
                     "studies": {"X_wd": ["owner_confirms_wd", "x_wd_committed"]}}],
    }


class Base(unittest.TestCase):
    def setUp(self):
        for p in (mock.patch.object(socket, "socket", _no_net), mock.patch.object(socket, "create_connection", _no_net),
                  mock.patch.object(socket, "getaddrinfo", _no_net), mock.patch.object(subprocess, "run", _no_proc),
                  mock.patch.object(subprocess, "Popen", _no_proc)):
            p.start()
            self.addCleanup(p.stop)
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        self.m = nr.load()


class Synthetic(Base):
    def setUp(self):
        super().setUp()
        self.sm = synthetic_matrix()
        self.od = os.path.join(self.tmp, "od.md")
        with open(self.od, "w", encoding="utf-8") as fh:
            fh.write("| # | x | y | flag | z |\n|---|---|---|---|---|\n"
                     "| D1 | lock X | - | `owner_confirms_x` | - |\n| D2 | key | - | `owner_key_x` | - |\n"
                     "| D3 | wd | - | `owner_confirms_wd` | - |\n")
        with open(os.path.join(self.tmp, "src.md"), "w", encoding="utf-8") as fh:
            fh.write("intro\nX_wd WITHDRAWN_BEFORE_LOCK here\nY READY\n")
        self.studies = ({"id": "X_wd", "matrix": "X_wd", "status": "WITHDRAWN_BEFORE_LOCK", "withdrawn": True,
                         "action": ("a_wd", "X_wd"), "note": "n", "sources": (("src.md", "WITHDRAWN_BEFORE_LOCK"),)},
                        {"id": "Y", "matrix": "Y", "status": "READY", "action": ("a_lock", "X"), "note": "n",
                         "sources": (("src.md", "Y READY"),)})

    def ev(self, at, flags=()):
        rep = gs.build(self.sm, at, root=self.tmp, matrix_path=os.path.join(self.tmp, "m.json"),
                       readiness_path=os.path.join(self.tmp, "r.md"), owner_path=self.od, flags=frozenset(flags),
                       studies=self.studies, deps=(), outside=())
        return {g["id"]: g for g in rep["gates"]}, rep

    def test_each_status_type(self):
        g, rep = self.ev(AFTER)
        self.assertEqual(g["S_DATE"]["status"], gs.READY)
        self.assertEqual(g["S_NEVER"]["status"], gs.BLOCKED)
        self.assertEqual(g["S_CONSTRAINT"]["status"], gs.READY)
        self.assertEqual(g["S_OWNER"]["status"], gs.NEEDS)
        self.assertEqual(g["S_WORK"]["status"], gs.BLOCKED)
        self.assertEqual(g["S_NODATE_OWNER"]["status"], gs.NEEDS)
        self.assertEqual(g["S_WD"]["status"], gs.WITHDRAWN)
        self.assertEqual(g["S_BADKIND"]["status"], gs.BLOCKED)
        self.assertEqual(g["S_LOCK"]["status"], gs.NEEDS)
        g, _ = self.ev(BEFORE)
        self.assertEqual(g["S_DATE"]["status"], gs.NOT_DUE)
        self.assertEqual(set(rep["counts"]), set(gs.STATUS_ORDER))

    def test_missing_requirements_are_listed(self):
        g, _ = self.ev(AFTER)
        self.assertEqual(g["S_OWNER"]["missing"], ["owner_confirms_x (D1)"])
        self.assertEqual(g["S_WORK"]["missing"], ["x_committed"])
        lock = g["S_LOCK"]
        # smallest route for X (a_lock, not a_lock_more); X_wd withdrawn; Y has no action through the gate
        self.assertEqual(lock["per_study"]["X"], (gs.NEEDS, ["owner_confirms_x (D1)", "x_committed"]))
        self.assertEqual(lock["per_study"]["X_wd"][0], gs.WITHDRAWN)
        self.assertEqual(lock["per_study"]["Y"][0], gs.BLOCKED)
        g, _ = self.ev(BEFORE)
        self.assertEqual(g["S_OWNER"]["missing"], ["dato %s" % AT, "owner_confirms_x (D1)"])
        self.assertTrue(any(m.startswith("X: owner_confirms_x (D1)") for m in g["S_LOCK"]["missing"]))

    def test_1114_boundary(self):
        g0, _ = self.ev(BEFORE, {"owner_confirms_x", "x_committed", "owner_key_x"})
        g1, _ = self.ev(AT, {"owner_confirms_x", "x_committed", "owner_key_x"})
        for gid in ("S_DATE", "S_OWNER", "S_WORK", "S_LOCK"):
            self.assertEqual(g0[gid]["status"], gs.NOT_DUE, gid)       # flags never help before the date
            self.assertEqual(g1[gid]["status"], gs.READY, gid)
        self.assertEqual(g0["S_NODATE_OWNER"]["status"], gs.READY)      # no date: flags alone decide

    def test_withdrawn_stays_withdrawn(self):
        every = {"owner_confirms_x", "x_committed", "owner_key_x", "owner_confirms_wd", "x_wd_committed"}
        for at in (BEFORE, AT, AFTER, LATE, "2027-01-01T00:00:00Z"):
            g, _ = self.ev(at, every)
            self.assertEqual(g["S_WD"]["status"], gs.WITHDRAWN, at)
            self.assertEqual(g["S_LOCK"]["per_study"]["X_wd"][0], gs.WITHDRAWN, at)

    def test_withdrawal_needs_its_source(self):
        bad = ({**self.studies[0], "sources": (("src.md", "NOT IN THE FILE"),)},)
        rep = gs.build(self.sm, AFTER, root=self.tmp, matrix_path=os.path.join(self.tmp, "m.json"),
                       readiness_path=os.path.join(self.tmp, "r.md"), owner_path=self.od, studies=bad, deps=(),
                       outside=())
        g = {x["id"]: x for x in rep["gates"]}
        self.assertEqual(rep["studies"][0]["status"], "UNVERIFIED_SOURCE")
        self.assertEqual(g["S_WD"]["status"], gs.NEEDS)                 # not withdrawn -> evaluated, still closed

    def test_owner_items_need_approval_even_after_the_date(self):
        for at in (AT, AFTER, LATE):
            g, _ = self.ev(at, {"x_committed"})
            self.assertEqual(g["S_OWNER"]["status"], gs.NEEDS, at)
            self.assertEqual(g["S_LOCK"]["status"], gs.NEEDS, at)

    def test_ready_never_beyond_the_readiness_evaluator(self):
        for at in (BEFORE, AT, AFTER):
            for flags in ((), ("owner_confirms_x", "x_committed")):
                g, _ = self.ev(at, flags)
                for gate in self.sm["gates"]:
                    if g[gate["id"]]["status"] == gs.READY:
                        self.assertEqual(nr.gate_status(gate, at, frozenset(flags)), "OPEN", (gate["id"], at))


class RealMatrix(Base):
    def rep(self, at):
        return gs.build(self.m, at)

    def gates(self, at):
        return {g["id"]: g for g in self.rep(at)["gates"]}

    def test_1114_boundary_real(self):
        b, a = self.gates(BEFORE), self.gates(AT)
        for gid in ("G01_HIST_1114", "G13_LOCK_A", "G17_F2_CALIBRATION", "G18_C1_ACTIVATION", "G16_F2_WINDOW"):
            self.assertEqual(b[gid]["status"], gs.NOT_DUE, gid)
            self.assertEqual(a[gid]["status"], gs.NEEDS, gid)
        self.assertIn("dato 2026-11-14T00:00:00Z", b["G01_HIST_1114"]["missing"])
        for gid in ("G09_COINM_1128", "G11_RESTART_1128", "G25_F3_DEFERRED", "G23_PAIRS_1119", "G24_S1_EVAL"):
            self.assertEqual(a[gid]["status"], gs.NOT_DUE, gid)
        self.assertEqual(a["G21_HFC1_3D"]["status"], gs.READY)
        self.assertEqual(b["G22_STRAKS_7D"]["status"], gs.READY)

    def test_b_n4_gates_withdrawn_and_closed(self):
        for at in (BEFORE, AFTER, LATE):
            g = self.gates(at)
            self.assertEqual(g["G14_LOCK_B"]["status"], gs.WITHDRAWN)
            self.assertEqual(g["G08_UPBIT_N4"]["status"], gs.WITHDRAWN)
            self.assertEqual(g["G01_HIST_1114"]["per_study"]["B_n4"][0], gs.WITHDRAWN)
            self.assertFalse(nr.decide(self.m, "upbit_fetch", at, "B_n4")[0])

    def test_owner_gates_after_the_date(self):
        g = self.gates(LATE)
        for gid in ("G13_LOCK_A", "G15_OWNER_SIGNATURE", "G16_F2_WINDOW", "G17_F2_CALIBRATION", "G18_C1_ACTIVATION",
                    "G19_FWD_KLINE_SOURCE", "G20_W0_ALPHA", "G01_HIST_1114"):
            self.assertEqual(g[gid]["status"], gs.NEEDS, gid)
        self.assertIn("owner_confirms_lock_A (D1)", g["G13_LOCK_A"]["missing"])
        for gid in ("G03_HOLDOUT_2024", "G04_RESERVED_2025PLUS", "G07_QUARANTINE", "G12_PMLP", "G26_S2_S3",
                    "G27_NO_REAL_MONEY", "G28_NO_ASSISTANT_SIGNATURE"):
            self.assertEqual(g[gid]["status"], gs.BLOCKED, gid)

    def test_known_study_statuses_are_found_in_their_sources(self):
        rows = {s["id"]: s for s in self.rep(AFTER)["studies"]}
        want = {"F2": "BLOCKED", "A_n6": "READY_NOT_LOCKED", "B_n4": "WITHDRAWN_BEFORE_LOCK", "C1": "READY_NOT_ACTIVE",
                "W0": "0.0375_LEFT_NO_RANKING_ACCEPTED", "HFC1": "DESCRIPTIVE", "S1": "OBSERVATION"}
        for k, v in want.items():
            self.assertEqual(rows[k]["status"], v, (k, rows[k]["sources"]))
            self.assertTrue(rows[k]["verified"])
        self.assertTrue(any(c.startswith("research/reviews/INBOX.md:") for c in rows["B_n4"]["sources"]))
        self.assertFalse(rows["A_n6"]["action_allowed"])

    def test_dns_dependency_is_listed(self):
        rep = self.rep(AFTER)
        deps = {d["id"]: d for d in rep["dependencies"]}
        listed = {h for d in rep["dependencies"] for h, _ in d["hosts"]}
        for h in gs.DNS_BLOCKED_HOSTS:
            self.assertIn(h, listed)
        for k in ("HFC1", "F2", "A_n6", "pm_lp (collector)"):
            self.assertTrue(deps[k]["dns_affected"], k)
        self.assertFalse(deps["STRAKS"]["dns_affected"])
        self.assertIn(("data-api.binance.vision", gs.DNS_LABEL), deps["HFC1"]["hosts"])
        for d in rep["dependencies"]:
            self.assertTrue(d["sources_ok"], (d["id"], d["sources"]))
        md = gs.render(rep)
        self.assertIn("BLOKERET (lokal DNS)", md)
        self.assertIn("2026-11-06..09", md)
        self.assertIn("getent hosts", md)
        self.assertIn("`getent` ikke kørt", md)

    def test_check_dns_uses_only_the_injected_runner(self):
        answers = {"data-api.binance.vision": (0, "::            data-api.binance.vision\n"),
                   "data.binance.vision": (0, "0.0.0.0       data.binance.vision\n"),
                   "clob.polymarket.com": (0, "104.18.1.1    clob.polymarket.com\n"),
                   "gamma-api.polymarket.com": (2, "")}
        res = gs.check_dns(runner=lambda h: answers[h])
        self.assertTrue(res["data-api.binance.vision"].startswith(gs.DNS_LABEL))
        self.assertTrue(res["data.binance.vision"].startswith(gs.DNS_LABEL))
        self.assertTrue(res["clob.polymarket.com"].startswith("OPLØSES"))
        self.assertTrue(res["gamma-api.polymarket.com"].startswith("IKKE FUNDET"))
        with mock.patch.object(gs, "_getent_runner", lambda h: answers[h]), \
                mock.patch("sys.stdout", new_callable=io.StringIO) as out:
            self.assertEqual(gs.main(["--at", AFTER, "--check-dns"]), 0)
        self.assertIn("`--check-dns` (getent)", out.getvalue())

    def test_pins_ok_and_reported(self):
        rep = self.rep(AFTER)
        self.assertEqual(rep["verify_hashes"], [])
        self.assertEqual(rep["validate"], [])
        self.assertIn("Pins (`nov14_readiness.verify_hashes`): OK", gs.render(rep))
        bad = copy.deepcopy(self.m)
        bad["protocol_identities"][0]["sha256"] = "0" * 64
        self.assertIn("MISMATCH", gs.render(gs.build(bad, AFTER)))


class ReadOnlyAndDeterministic(Base):
    def test_no_network_or_subprocess_by_default(self):
        with mock.patch("sys.stdout", new_callable=io.StringIO) as out:
            self.assertEqual(gs.main(["--at", AFTER]), 0)
        self.assertIn(gs.NO_LOCK_LINE, out.getvalue())
        with open(gs.__file__, encoding="utf-8") as fh:
            src = fh.read()
        for bad in ("import socket", "urllib", "http.client", "requests", "sqlite3", "api.upbit.com/"):
            self.assertNotIn(bad, src)
        self.assertEqual(src.count("import subprocess"), 1)              # only inside _getent_runner

    def test_never_writes_protected_files(self):
        before = {p: _sha(p) for p in PROTECTED}
        out = os.path.join(self.tmp, "preview.md")
        self.assertEqual(gs.main(["--at", AFTER, "--out", out, "--preview-generated-on", "2026-11-09"]), 0)
        with mock.patch("sys.stdout", new_callable=io.StringIO), mock.patch("sys.stderr", new_callable=io.StringIO):
            for p in PROTECTED + ("research/reviews/INBOX.md", "research/PROTOCOL_V3.md"):
                self.assertEqual(gs.main(["--at", AFTER, "--out", os.path.join(HERE, p)]), 2, p)
            self.assertEqual(gs.main(["--at", AFTER, "--out", os.path.join(self.tmp, "x.json")]), 2)
            self.assertEqual(gs.main(["--at", "2026-11-14 00:30"]), 2)
        self.assertEqual(before, {p: _sha(p) for p in PROTECTED})
        with open(out, encoding="utf-8") as fh:
            text = fh.read()
        self.assertIn("PREVIEW — genereret 2026-11-09", text)
        self.assertIn("IKKE 14/11-statusrapporten", text)

    def test_forbidden_paths_are_never_opened(self):
        with mock.patch("builtins.open", side_effect=AssertionError("opened")):
            with self.assertRaises(nr.MatrixError):
                gs.find_line("research/data/N4_KIMCHI_PAIRS_2026-11-02.json", "x")
            with self.assertRaises(nr.MatrixError):
                gs.find_line("../quarantine/anything.json", "x")

    def test_deterministic_output(self):
        a = gs.render(gs.build(self.m, AFTER), "2026-11-09")
        b = gs.render(gs.build(self.m, AFTER), "2026-11-09")
        self.assertEqual(a, b)
        o1, o2 = os.path.join(self.tmp, "a.md"), os.path.join(self.tmp, "b.md")
        gs.main(["--at", AFTER, "--out", o1])
        gs.main(["--at", AFTER, "--out", o2])
        with open(o1, "rb") as f1, open(o2, "rb") as f2:
            self.assertEqual(f1.read(), f2.read())
        self.assertEqual(a.count(gs.NO_LOCK_LINE), 2)


if __name__ == "__main__":
    unittest.main()
