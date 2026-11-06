"""Director order 47 P0: factory register and multiple-testing ledger, on synthetic data only."""
import json
import os
import sqlite3
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from research.tools import factory as fa  # noqa: E402

VOCAB = {"tags": {"a_mom": {"related": ["b_mom"]}, "b_mom": {"related": []}, "c_carry": {"related": []}}}
T0 = 1_800_000_000                     # 2027-01-15, after the COIN-M date
SAFE = [{"path": "x.zip", "sha256": "ab" * 32, "window_start": 1_600_000_000, "window_end": 1_640_000_000,
         "source": "usdm"}]


def rec(**kw):
    r = {"family": "F1", "mechanism": "m", "mechanism_tag": "a_mom", "direction": 1, "universe": ["BTC", "ETH"],
         "windows": {"train": "2020"}, "sources": ["binance"], "datasets": SAFE, "parameter_family": {"k": [1, 2]},
         "estimand": "net mean daily", "benchmark": "bh", "cost_model": "catalogue", "rejection": "lb <= 0",
         "spec_commit": "c" * 40}
    r.update(kw)
    return r


def fresh():
    led = fa.Ledger()
    return led, fa.Register(led, fa.lineages(VOCAB))


def to_frozen(reg, hid="H1", **kw):
    reg.propose(hid, rec(**kw), T0)
    reg.move(hid, "APPROVED", T0 + 1, {"actor": "human:owner"})
    reg.move(hid, "FROZEN", T0 + 2)


class Lineage(unittest.TestCase):
    def test_related_tags_share_a_lineage(self):
        lm = fa.lineages(VOCAB)
        self.assertEqual(lm["a_mom"], lm["b_mom"])
        self.assertNotEqual(lm["a_mom"], lm["c_carry"])
        self.assertEqual(fa.lineage_of("zzz", lm), ("zzz", False))

    def test_rename_does_not_reset(self):
        led, reg = fresh()
        reg.propose("H1", rec(), T0)
        with self.assertRaises(fa.FactoryError):
            reg.propose("H1_renamed", rec(), T0)
        reg.propose("H2", rec(mechanism_tag="b_mom", estimand="other"), T0)
        self.assertEqual(reg.recs["H1"]["lineage"], reg.recs["H2"]["lineage"])


class LedgerRules(unittest.TestCase):
    def test_no_refund_and_every_attempt_counts(self):
        led = fa.Ledger()
        with self.assertRaises(fa.FactoryError):
            led.charge("H", "L", T0, 1, -0.01, "t")
        with self.assertRaises(fa.FactoryError):
            led.charge("H", "L", T0, 0, 0.01, "t")
        led.charge("H", "L", T0, 3, 0.01, "t")
        led.charge("H", "L", T0 + 5, 2, 0.0, "t")
        self.assertEqual(led.totals()["L"], {"attempts": 2, "variants": 5, "alpha": 0.01, "hypotheses": 1})
        self.assertTrue(led.verify())

    def test_tampering_is_detected(self):
        led = fa.Ledger()
        led.charge("H", "L", T0, 3, 0.01, "t")
        led.charge("H", "L", T0, 3, 0.01, "t")
        led.entries[0]["alpha"] = 0.0
        with self.assertRaises(fa.FactoryError):
            led.verify()


class StateMachine(unittest.TestCase):
    def test_approval_needs_a_human(self):
        _, reg = fresh()
        reg.propose("H1", rec(), T0)
        for actor in (None, "claude", "system:auto", "chatgpt"):
            with self.assertRaises(fa.FactoryError):
                reg.move("H1", "APPROVED", T0 + 1, {"actor": actor})

    def test_no_skipping(self):
        _, reg = fresh()
        reg.propose("H1", rec(), T0)
        for to in ("FROZEN", "TESTED", "VALIDATED"):
            with self.assertRaises(fa.FactoryError):
                reg.move("H1", to, T0 + 1, {"actor": "human:owner"})

    def test_freeze_needs_full_prereg_and_hashes(self):
        _, reg = fresh()
        reg.propose("H1", rec(estimand=""), T0)
        reg.move("H1", "APPROVED", T0 + 1, {"actor": "human:owner"})
        with self.assertRaises(fa.FactoryError):
            reg.move("H1", "FROZEN", T0 + 2)
        reg.propose("H2", rec(mechanism_tag="c_carry", datasets=[{**SAFE[0], "sha256": ""}]), T0)
        reg.move("H2", "APPROVED", T0 + 1, {"actor": "human:owner"})
        with self.assertRaises(fa.FactoryError):
            reg.move("H2", "FROZEN", T0 + 2)

    def test_protected_windows(self):
        hold = [{**SAFE[0], "window_start": 1_710_000_000, "window_end": 1_712_000_000}]      # March 2024
        _, reg = fresh()
        reg.propose("H1", rec(datasets=hold), T0)
        reg.move("H1", "APPROVED", T0 + 1, {"actor": "human:owner"})
        with self.assertRaises(fa.FactoryError):
            reg.move("H1", "FROZEN", T0 + 2)
        coinm = [{**SAFE[0], "source": "Binance COIN-M"}]
        self.assertTrue(fa.protected(coinm, fa.COINM_FROM - 1))
        self.assertFalse(fa.protected(coinm, fa.COINM_FROM))

    def test_test_needs_a_fresh_charge(self):
        led, reg = fresh()
        to_frozen(reg)
        led.charge("H1", "a_mom", T0 + 1, 2, 0.005, "t")         # before the freeze: does not count
        with self.assertRaises(fa.FactoryError):
            reg.move("H1", "TESTED", T0 + 3)
        led.charge("H1", "a_mom", T0 + 3, 2, 0.005, "t")
        reg.move("H1", "TESTED", T0 + 4)
        reg.move("H1", "INCONCLUSIVE", T0 + 5)
        with self.assertRaises(fa.FactoryError):                 # retest needs another charge
            reg.move("H1", "TESTED", T0 + 6)
        led.charge("H1", "a_mom", T0 + 6, 1, 0.005, "t")
        reg.move("H1", "TESTED", T0 + 7)
        reg.move("H1", "REJECTED", T0 + 8)
        with self.assertRaises(fa.FactoryError):                 # final: alpha is not reused
            reg.move("H1", "TESTED", T0 + 9)

    def test_changed_data_or_prereg_after_lock(self):
        led, reg = fresh()
        to_frozen(reg)
        led.charge("H1", "a_mom", T0 + 3, 1, 0.005, "t")
        with self.assertRaises(fa.FactoryError):
            reg.move("H1", "TESTED", T0 + 4, {"datasets": [{**SAFE[0], "sha256": "cd" * 32}]})
        reg.recs["H1"]["estimand"] = "something nicer"
        with self.assertRaises(fa.FactoryError):
            reg.move("H1", "TESTED", T0 + 4)

    def test_never_promotes_to_paper(self):
        led, reg = fresh()
        to_frozen(reg)
        led.charge("H1", "a_mom", T0 + 3, 1, 0.005, "t")
        reg.move("H1", "TESTED", T0 + 4)
        with self.assertRaises(fa.FactoryError):
            reg.move("H1", "VALIDATED", T0 + 5, {"promote_to_paper": True})


def synthetic_db():
    con = sqlite3.connect(":memory:")
    con.executescript("""
    CREATE TABLE experiments(id INTEGER PRIMARY KEY, exp_id, version, created_ts, mechanism_tag, fingerprint, spec_json,
                             spec_path, spec_commit, code_hash, note);
    CREATE TABLE transitions(id INTEGER PRIMARY KEY, exp_id, ts, from_state, to_state, actor, reason, evidence);
    CREATE TABLE trials(id INTEGER PRIMARY KEY, exp_id, ts, variant, split, sharpe_daily, n_days, net_total, params);
    CREATE TABLE datasets(id INTEGER PRIMARY KEY, exp_id, split, source, path, window_start, window_end, ts, sha256,
                          size, purpose, code_hash);
    CREATE TABLE results(id INTEGER PRIMARY KEY, exp_id, version, ts, label, verdict, metrics, evidence, supersedes);
    CREATE TABLE alpha_ledger(id INTEGER PRIMARY KEY, exp_id, ts, alpha, note);
    CREATE TABLE events(id INTEGER PRIMARY KEY, ts, kind, actor, exp_id, payload);
    """)
    con.executemany("INSERT INTO experiments(exp_id,version,created_ts,mechanism_tag,spec_json) VALUES(?,?,?,?,?)",
                    [("E1", 1, 10, "a_mom", "{}"), ("E1", 2, 20, "a_mom", "{}"), ("E2", 1, 30, "c_carry", "{}"),
                     ("E3", 1, 40, "nope", "{}")])
    con.executemany("INSERT INTO transitions(exp_id,to_state) VALUES(?,?)",
                    [("E1", "DISCOVERED"), ("E1", "REJECTED"), ("E2", "OBSERVATION"), ("E3", "REJECTED")])
    con.executemany("INSERT INTO trials(exp_id,split) VALUES(?,?)", [("E1", "train")] * 3)
    con.executemany("INSERT INTO alpha_ledger(exp_id,alpha) VALUES(?,?)",
                    [("E2", 0.01), ("family:x", 0.02), ("family:x", -0.01)])
    con.executemany("INSERT INTO events(kind,payload) VALUES(?,?)", [
        ("research.hypothesis", json.dumps({"key": "t|o|m", "type": "t"})),
        ("research.hypothesis_screen", json.dumps({"key": "t|o|m", "type": "t"})),
        ("research.measurement", json.dumps({"hypothesis": "t|o|m", "alpha": 0.003})),
        ("research.explore", json.dumps({"candidates": ["a", "b", "c"]})),
        ("research.explore", json.dumps({"candidates": ["a", "c"]}))])
    return con


class Snapshot(unittest.TestCase):
    def test_snapshot_counts_everything(self):
        offdb = [{"id": "S1", "attempts": 4, "alpha": 0.0, "lineage": "L", "note": ""},
                 {"id": "S2", "attempts": None, "alpha": None, "lineage": None, "note": ""}]
        rep = fa.snapshot(synthetic_db(), VOCAB, offdb)
        self.assertEqual(rep["by_status"], {"INCONCLUSIVE": 1, "REJECTED": 2})
        self.assertEqual(rep["gaps"]["tag_outside_vocabulary"], ["nope"])
        self.assertEqual(rep["gaps"]["tested_without_trials_or_alpha (counted as 1 attempt)"], ["E3"])
        self.assertEqual(rep["gaps"]["offdb_unknown_fields"], ["S2"])
        self.assertEqual(rep["alpha_offsets"], {"family:x": -0.01})
        self.assertEqual(rep["family_alpha_rows"], {"family:x": {"reserved": 0.02, "offset": -0.01}})
        lg = rep["ledger"]
        # E1 3 trials, E2 alpha only (1), E3 legacy (1), m17 screen+measurement (2), explore 3 unique, S1 4
        self.assertEqual(lg["variants"], 3 + 1 + 1 + 2 + 3 + 4)
        self.assertAlmostEqual(lg["alpha_gross"], 0.01 + 0.003)

    def test_reproducible(self):
        a = fa.snapshot(synthetic_db(), VOCAB, [])
        b = fa.snapshot(synthetic_db(), VOCAB, [])
        self.assertEqual(fa.sha(a), fa.sha(b))


if __name__ == "__main__":
    unittest.main()
