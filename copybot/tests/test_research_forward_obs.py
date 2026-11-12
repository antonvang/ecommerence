"""Director order 50 P1: the forward data observatory's quality model (research/tools/forward_obs.py), synthetic only.

Every fault the simulator injects must be found, clean data must pass, and the module must make no network call and
write nothing except where a caller points write_report."""
import ast
import builtins
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
import forward_obs as fo  # noqa: E402

SRC = os.path.join(HERE, "research", "tools", "forward_obs.py")
SCHEMA_JSON = os.path.join(HERE, "research", "desk", "data_quality_schema.json")
REGISTRY = os.path.join(HERE, "research", "desk", "stream_registry.json")


def run(faults=True, seed=50, claims=None):
    recs, truth, p = fo.simulate(seed=seed, faults=faults)
    rep = fo.assess(recs, p["start"], p["end"], p["cadence"], claims or [], now=p["end"] + 7200)
    return rep, truth, p, recs


def keyed(findings, name):
    return {(tuple(x["key"]), x["ts"]) for x in findings[name]}


class Clean(unittest.TestCase):
    def test_clean_data_passes(self):
        for seed in (1, 50, 99):
            rep, truth, p, _ = run(faults=False, seed=seed)
            self.assertEqual(truth, [])
            self.assertTrue(rep["ok"], {k: v for k, v in rep["errors"].items() if v})
            self.assertEqual({k: v for k, v in rep["warnings"].items() if v}, {})
            self.assertEqual(rep["totals"]["coverage_pct"], 100.0)
            self.assertEqual((rep["totals"]["missing"], rep["totals"]["dropped"]), (0, 0))
            self.assertGreater(rep["basis_derived"], 0)
            self.assertGreater(rep["forecast_pairs"], 0)

    def test_listing_and_delisting_are_information_not_gaps(self):
        rep, _, p, _ = run(faults=False)
        f = rep["findings"]
        self.assertEqual([(x["symbol"], x["first_seen"]) for x in f["listings"]], [(p["list_sym"], p["list_ts"])])
        self.assertEqual([(x["symbol"], x["gone_at"]) for x in f["delistings"]], [(p["delist_sym"], p["delist_ts"])])
        self.assertLess(f["listings"][0]["listed_after"], p["list_ts"])          # snapshot resolution is explicit
        for sym in (p["list_sym"], p["delist_sym"]):
            c = rep["coverage"][f"syn_book|book|synx:perp|{sym}"]
            self.assertEqual(c["coverage_pct"], 100.0)
            self.assertLess(c["expected"], rep["coverage"]["syn_book|book|synx:perp|AAA"]["expected"])

    def test_deterministic(self):
        a, b = run(seed=50)[0], run(seed=50)[0]
        self.assertEqual(fo.report_sha256(a), fo.report_sha256(b))
        self.assertNotEqual(fo.report_sha256(a), fo.report_sha256(run(seed=51)[0]))


class InjectedFaults(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rep, cls.truth, cls.p, cls.recs = run(faults=True)
        cls.f = cls.rep["findings"]

    def faults(self, name):
        return [t for t in self.truth if t["fault"] == name]

    def test_every_fault_kind_was_injected(self):
        kinds = {t["fault"] for t in self.truth}
        self.assertEqual(kinds, {"gap", "stale", "duplicate", "conflicting_duplicate", "crossed", "out_of_order",
                                 "basis_time_mismatch", "bad_funding_interval", "lookahead", "revised", "tampered"})
        self.assertFalse(self.rep["ok"])

    def test_gaps_listed_explicitly_with_slot_counts(self):
        got = {(tuple(g["key"]), g["missing_slots"]) for g in self.f["gaps"]}
        for t in self.faults("gap"):
            self.assertIn((tuple(t["key"]), t["steps"]), got)
        missing = sum(c["missing"] for c in self.rep["coverage"].values())
        self.assertEqual(missing, sum(t["steps"] for t in self.faults("gap")))     # never filled

    def test_missing_and_dropped_counted_separately(self):
        cov = self.rep["coverage"]
        gap_a = cov["syn_book|book|synx:perp|AAA"]
        self.assertEqual((gap_a["missing"], gap_a["dropped"]), (4, 0))
        crossed_and_stale = cov["syn_book|book|synx:perp|BBB"]          # 3 stale + 1 crossed arrived, rejected
        self.assertEqual((crossed_and_stale["missing"], crossed_and_stale["dropped"]), (0, 4))
        t = self.rep["totals"]
        self.assertEqual(t["expected"], t["valid"] + t["dropped"] + t["missing"])

    def test_stale_quotes(self):
        got = keyed(self.f, "stale")
        for t in self.faults("stale"):
            self.assertIn((tuple(t["key"]), t["ts"]), got)

    def test_duplicates_exact_and_conflicting(self):
        for name in ("duplicate", "conflicting_duplicate"):
            got = keyed(self.f, name)
            self.assertTrue(self.faults(name))
            for t in self.faults(name):
                self.assertIn((tuple(t["key"]), t["ts"]), got)

    def test_crossed_book(self):
        got = keyed(self.f, "crossed")
        for t in self.faults("crossed"):
            self.assertIn((tuple(t["key"]), t["ts"]), got)

    def test_out_of_order(self):
        got = keyed(self.f, "out_of_order")
        for t in self.faults("out_of_order"):
            self.assertIn((tuple(t["key"]), t["ts"]), got)

    def test_basis_only_from_same_time_legs(self):
        got = {(m["symbol"], m["slot"]) for m in self.f["basis_time_mismatch"]}
        for t in self.faults("basis_time_mismatch"):
            self.assertIn((t["symbol"], t["slot"]), got)

    def test_funding_interval(self):
        got = {tuple(x["key"]) for x in self.f["bad_funding_interval"]}
        for t in self.faults("bad_funding_interval"):
            self.assertIn(tuple(t["key"]), got)

    def test_forecast_freeze(self):
        for name in ("lookahead", "revised", "tampered"):
            self.assertEqual(len(self.f[name]), len(self.faults(name)), name)
        self.assertEqual(self.f["lookahead"][0]["target_start"], self.faults("lookahead")[0]["target_start"])

    def test_no_unexplained_errors(self):
        expected = {"gaps": 3,        # perp AAA 4 slots, spot CCC 3 slots, and BBB's 3 stale samples left a gap
                    "stale": 3, "duplicate": 1, "conflicting_duplicate": 1, "crossed": 1, "out_of_order": 1,
                    "basis_time_mismatch": 1, "bad_funding_interval": 1, "lookahead": 1, "revised": 1,
                    "tampered": 1, "pit_violations": 0, "survivorship_omissions": 0}
        for k, v in expected.items():
            self.assertEqual(self.rep["errors"][k], v, k)
        others = {k: v for k, v in self.rep["errors"].items() if k not in expected and v}
        self.assertEqual(others, {})


class PointInTimeUniverse(unittest.TestCase):
    def setUp(self):
        recs, _, self.p = fo.simulate(faults=False)[0], None, fo.simulate(faults=False)[2]
        self.versions = fo.universe_versions(recs)

    def test_symbol_first_seen_at_t_cannot_appear_before_t(self):
        p = self.p
        claims = [{"as_of": p["list_ts"] - 1, "symbols": ["AAA", "BBB", "CCC", p["delist_sym"], p["list_sym"]]},
                  {"as_of": p["list_ts"], "symbols": ["AAA", "BBB", "CCC", p["delist_sym"], p["list_sym"]]},
                  {"as_of": p["start"], "symbols": ["AAA", "ZZZ_UNKNOWN"]}]
        f = fo.check_universe_pit(claims, self.versions)
        got = {(v["as_of"], v["symbol"]) for v in f["pit_violations"]}
        self.assertEqual(got, {(p["list_ts"] - 1, p["list_sym"]), (p["start"], "ZZZ_UNKNOWN")})

    def test_survivorship_omission(self):
        p = self.p
        f = fo.check_universe_pit([{"as_of": p["delist_ts"] - 60, "symbols": ["AAA", "BBB", "CCC", p["list_sym"]]}],
                                  self.versions)
        self.assertEqual([x["symbol"] for x in f["survivorship_omissions"]], [p["delist_sym"]])
        f = fo.check_universe_pit([{"as_of": p["delist_ts"], "symbols": ["AAA", "BBB", "CCC", p["list_sym"]]}],
                                  self.versions)
        self.assertEqual(f, {"pit_violations": [], "survivorship_omissions": []})

    def test_live_at(self):
        p = self.p
        self.assertNotIn(p["list_sym"], fo.live_at(self.versions, p["list_ts"] - 1))
        self.assertIn(p["list_sym"], fo.live_at(self.versions, p["list_ts"]))
        self.assertIn(p["delist_sym"], fo.live_at(self.versions, p["delist_ts"] - 1))
        self.assertNotIn(p["delist_sym"], fo.live_at(self.versions, p["delist_ts"]))

    def test_faulty_run_reports_pit_violation(self):
        p = fo.simulate(faults=True)[2]
        rep = run(faults=True, claims=[{"as_of": p["list_ts"] - 1, "symbols": [p["list_sym"], "AAA", "BBB", "CCC",
                                                                                 p["delist_sym"]]}])[0]
        self.assertEqual([v["symbol"] for v in rep["findings"]["pit_violations"]], [p["list_sym"]])

    def test_spec_change_and_relisting(self):
        u = lambda ts, sym, st="TRADING", tick=0.01: {"kind": "universe", "stream": "u", "ts": ts, "venue": "v",  # noqa
                                                    "symbol": sym, "status": st, "tick_size": tick}
        recs = [u(0, "A"), u(0, "B"), u(10, "A", tick=0.001), u(10, "B", st="BREAK"), u(20, "A"), u(20, "B")]
        v = fo.universe_versions(recs)
        self.assertEqual([(c["symbol"], c["ts"]) for c in v["spec_changes"]], [("A", 10), ("A", 20)])
        self.assertEqual([(d["symbol"], d["gone_at"], d["status"]) for d in v["delistings"]], [("B", 10, "BREAK")])
        self.assertEqual([(r["symbol"], r["first_seen"]) for r in v["relistings"]], [("B", 20)])
        self.assertEqual(fo.live_at(v, 15), ["A"])


class Units(unittest.TestCase):
    def test_schema_types(self):
        ok = {"kind": "book", "stream": "s", "ts": 1.0, "venue": "v", "symbol": "X", "market": "perp", "bid": 1.0,
              "ask": 1.1, "bid_qty": 0, "ask_qty": 2, "quote_ts": None}
        self.assertEqual(fo.validate_record(ok), [])
        self.assertIn("bad type bid", fo.validate_record(dict(ok, bid=True)))
        self.assertIn("bad type bid", fo.validate_record(dict(ok, bid=float("nan"))))
        self.assertIn("missing ask", fo.validate_record({k: v for k, v in ok.items() if k != "ask"}))
        self.assertIn("bad value market", fo.validate_record(dict(ok, market="option")))
        self.assertIn("unknown kind 'x'", fo.validate_record(dict(ok, kind="x")))
        acc, f = fo.screen_order([ok, dict(ok, ts="1"), "junk"])
        self.assertEqual((acc, len(f["invalid"])), ([0], 2))

    def test_suspected_stale_without_venue_time(self):
        b = {"kind": "book", "stream": "s", "venue": "v", "symbol": "X", "market": "spot", "bid": 1.0, "ask": 1.1,
             "bid_qty": 1.0, "ask_qty": 1.0}
        recs = [dict(b, ts=60.0 * i) for i in range(6)] + [dict(b, ts=360.0, bid=1.01)]
        bad, f = fo.check_books(recs, range(len(recs)), 60)
        self.assertEqual(bad, set())
        self.assertEqual(len(f["stale_suspected"]), 1)
        self.assertEqual(f["stale_suspected"][0]["first_index"], 0)

    def test_locked_book_is_a_warning(self):
        b = {"kind": "book", "stream": "s", "venue": "v", "symbol": "X", "market": "spot", "bid": 1.0, "ask": 1.0,
             "bid_qty": 1.0, "ask_qty": 1.0, "ts": 0.0, "quote_ts": 0.0}
        bad, f = fo.check_books([b], [0], 60)
        self.assertEqual((bad, len(f["locked"])), (set(), 1))

    def test_funding_step_mismatch(self):
        r = {"kind": "funding", "stream": "f", "venue": "v", "symbol": "X", "rate": 0.0001, "interval_h": 8}
        recs = [dict(r, ts=1, funding_time=0), dict(r, ts=2, funding_time=8 * 3600), dict(r, ts=3, funding_time=12 * 3600),
                dict(r, ts=4, funding_time=20 * 3600, rate=0.5)]
        bad, f = fo.check_funding(recs, range(4))
        self.assertEqual(len(f["funding_step_mismatch"]), 1)
        self.assertEqual(len(f["funding_rate_out_of_range"]), 1)
        self.assertEqual(bad, {3})

    def test_stored_basis_recomputed(self):
        spot = {"ts": 0.0, "bid": 99.0, "ask": 101.0, "venue": "v", "symbol": "X"}
        perp = {"ts": 1.0, "bid": 100.0, "ask": 102.0, "venue": "v", "symbol": "X"}
        good = fo.basis_record(spot, perp)
        bad_val = dict(good, basis=good["basis"] + 1e-4)
        far = dict(good, perp_ts=good["spot_ts"] + 6)
        bad, f = fo.check_basis([good, bad_val, far], [0, 1, 2])
        self.assertEqual(bad, {1, 2})
        self.assertEqual((len(f["basis_recompute_mismatch"]), len(f["basis_time_mismatch"])), (1, 1))

    def test_gap_edges(self):
        g = fo.find_gaps([300.0, 360.0], 0, 1000, 60)
        self.assertEqual([(x["edge"], x["missing_slots"]) for x in g], [("start", 5), ("end", 10)])
        self.assertEqual(fo.find_gaps([], 0, 600, 60)[0]["missing_slots"], 10)
        self.assertEqual(fo.find_gaps([0.0, 60.5, 121.0], 0, 180, 60), [])

    def test_schema_file_matches_module(self):
        with open(SCHEMA_JSON, encoding="utf-8") as fh:
            self.assertEqual(json.load(fh), json.loads(json.dumps(fo.SCHEMA)))

    def test_registry_is_well_formed(self):
        with open(REGISTRY, encoding="utf-8") as fh:
            reg = json.load(fh)
        allowed = {"EXISTING_ACTIVE", "EXISTING_INACTIVE", "PROPOSED_NEEDS_SEPARATE_APPROVAL", "REJECTED_DUPLICATE",
                   "APPROVED"}
        need = {"id", "status", "source_host", "fields", "cadence_s", "storage", "started", "consumers", "gate",
                "est_weekly_bytes", "est_weekly_requests", "notes"}
        ids = [s["id"] for s in reg["streams"]]
        self.assertEqual(len(ids), len(set(ids)))
        for s in reg["streams"]:
            self.assertTrue(need <= set(s), s["id"])
            self.assertTrue(s["status"] in allowed or s["status"].startswith("BLOCKED_UNTIL_"), s["id"])
            if s["status"] == "PROPOSED_NEEDS_SEPARATE_APPROVAL":
                self.assertTrue(s["gate"], s["id"])


class Isolation(unittest.TestCase):
    def test_imports_no_network_or_db_module(self):
        with open(SRC, encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        mods = set()
        for n in ast.walk(tree):
            if isinstance(n, ast.Import):
                mods |= {a.name.split(".")[0] for a in n.names}
            elif isinstance(n, ast.ImportFrom):
                mods.add((n.module or "").split(".")[0])
        self.assertEqual(mods & {"socket", "urllib", "http", "ssl", "requests", "sqlite3", "subprocess", "os",
                                 "shutil", "lab"}, set())

    def test_no_network_and_no_writes_outside_temp(self):
        tmp = tempfile.mkdtemp()
        opened, real_open = [], builtins.open

        def guarded_open(file, mode="r", *a, **k):
            if any(c in mode for c in "wax+"):
                opened.append(os.path.abspath(file))
            return real_open(file, mode, *a, **k)

        def no_net(*a, **k):
            raise AssertionError("network call attempted")

        cwd = os.getcwd()
        try:
            os.chdir(tmp)
            with mock.patch.object(socket, "socket", no_net), mock.patch.object(socket, "create_connection", no_net), \
                    mock.patch.object(socket, "getaddrinfo", no_net), mock.patch.object(builtins, "open", guarded_open):
                out = fo.selftest(seed=3)
                rep = run(faults=True, seed=3)[0]
                path = fo.write_report(rep, os.path.join(tmp, "report.json"))
            self.assertTrue(out["clean"]["ok"])
            self.assertFalse(out["faulty"]["ok"])
            self.assertEqual(opened, [os.path.abspath(path)])
            self.assertEqual(sorted(os.listdir(tmp)), ["report.json"])
        finally:
            os.chdir(cwd)
            shutil.rmtree(tmp)

    def test_gate_strings_absent(self):
        with open(SRC, encoding="utf-8") as fh:
            src = fh.read()
        for s in ("upbit", "news/1", "lab.db", "QUARANTINE", "dapi."):
            self.assertNotIn(s, src)

    def test_synthetic_window_is_not_a_real_period(self):
        _, _, p = fo.simulate(faults=False)
        self.assertGreater(p["start"], 1_900_000_000)


if __name__ == "__main__":
    import direct_guard  # noqa: E402,F401  (order 75: quarantine guard for direct runs)
    unittest.main()
