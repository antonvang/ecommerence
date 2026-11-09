"""Director order 75 P0: register V2 for future studies. Synthetic records only; no file is read."""
import copy
import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from research.tools import factory  # noqa: E402
from research.tools import register_snapshot as snap  # noqa: E402
from research.tools import register_stats as rs  # noqa: E402
from research.tools import register_v2 as v2  # noqa: E402

A, B, C = "a" * 64, "b" * 64, "c" * 64
EV = {"artifact": "synthetic/fixture.json", "sha256": A}
PROV = {"origin": "RUN_OUTPUT", "artifact": "synthetic/fixture.json", "sha256": A, "code_commit": "abc1234"}
SOURCE = os.path.join(HERE, "research", "tools", "register_v2.py")


def fields(**over):
    base = {
        "hypothesis_id": "H1", "lineage": "carry",
        "trial_universe": {"definition": "lookbacks 10..50", "size": 5, "members_sha256": A},
        "variants_tested": {"count": 5, "artifact": "synthetic/fixture.json", "sha256": B},
        "parameters": v2.parameters_block({"lookback": 20}), "code_hash": "abc1234",
        "data_source": {"name": "synthetic", "sha256": B},
        "data_period": {"start": "2025-01-01", "end": "2025-06-30"},
        "cost_model": {"name": "taker", "round_trip_bps": 12.0, "sha256": C},
        "evaluation_method": {"name": "sharpe-net", "sha256": A},
        "data_quality": {"status": "VERIFIED", "evidence": EV}, "deviations": [],
    }
    base.update(over)
    return base


def deviation(*names):
    return {"date": "2025-07-01", "fields": list(names), "description": "synthetic deviation"}


class Records(unittest.TestCase):
    def test_future_record_holds_every_field(self):
        rec = v2.record("R1", v2.FUTURE, **fields())
        self.assertEqual(v2.completeness(rec), {"status": v2.OK, "missing": []})
        for k in v2.FIELDS:
            self.assertNotEqual(rec[k], v2.MISSING_INPUT, k)

    def test_future_record_must_state_the_registration(self):
        for k in v2.LOCKED + ("data_quality", "deviations"):
            with self.assertRaises(v2.StatsError, msg=k):
                v2.record("R1", v2.FUTURE, **fields(**{k: None}))

    def test_future_record_may_wait_for_the_variant_count_only(self):
        rec = v2.record("R1", v2.FUTURE, **fields(variants_tested=None))
        self.assertEqual(rec["variants_tested"], v2.MISSING_INPUT)
        self.assertEqual(v2.completeness(rec)["missing"], ["variants_tested"])

    def test_historical_fields_stay_missing_and_nothing_is_filled(self):
        rec = v2.record("OLD", v2.HISTORICAL)
        for k in v2.FIELDS:
            self.assertEqual(rec[k], v2.MISSING_INPUT, k)
        self.assertEqual(v2.completeness(rec)["status"], v2.MISSING_INPUT)
        self.assertEqual(rec["deviations"], v2.MISSING_INPUT)     # unknown, not "none"
        self.assertNotIn("register_snapshot", rec)

    def test_none_is_absent_and_empty_deviations_are_a_statement(self):
        rec = v2.record("OLD", v2.HISTORICAL, deviations=[])
        self.assertEqual(rec["deviations"], [])
        self.assertEqual(v2.record("OLD", v2.HISTORICAL, deviations=None)["deviations"], v2.MISSING_INPUT)

    def test_a_documented_historical_value_still_needs_its_evidence(self):
        with self.assertRaises(v2.StatsError):
            v2.record("OLD", v2.HISTORICAL, variants_tested={"count": 40})
        rec = v2.record("OLD", v2.HISTORICAL, variants_tested={"count": 40, "artifact": "x", "sha256": A})
        self.assertEqual(rec["variants_tested"]["count"], 40)

    def test_field_formats(self):
        bad = {"trial_universe": {"definition": "x", "size": 0, "members_sha256": A},
               "variants_tested": {"count": 0, "artifact": "x", "sha256": A},
               "code_hash": "not hex", "data_source": {"name": "x", "sha256": "short"},
               "data_period": {"start": "2025-02-30", "end": "2025-06-30"},
               "cost_model": {"name": "x", "round_trip_bps": -1, "sha256": A},
               "evaluation_method": {"name": "", "sha256": A},
               "data_quality": {"status": "FINE", "evidence": EV},
               "deviations": [{"date": "2025-01-01", "fields": ["nope"], "description": "x"}]}
        for k, value in bad.items():
            with self.assertRaises(v2.StatsError, msg=k):
                v2.record("R1", v2.FUTURE, **fields(**{k: value}))
        with self.assertRaises(v2.StatsError):
            v2.record("R1", v2.FUTURE, **fields(data_period={"start": "2025-06-01", "end": "2025-01-01"}))
        with self.assertRaises(v2.StatsError):
            v2.record("R1", v2.FUTURE, nonsense=1, **fields())

    def test_parameters_hash_is_checked_against_the_values(self):
        block = v2.parameters_block({"lookback": 20})
        block["values"]["lookback"] = 21
        with self.assertRaises(v2.StatsError):
            v2.record("R1", v2.FUTURE, **fields(parameters=block))

    def test_data_quality_needs_evidence_unless_not_checked(self):
        with self.assertRaises(v2.StatsError):
            v2.record("R1", v2.FUTURE, **fields(data_quality={"status": "VERIFIED"}))
        rec = v2.record("R1", v2.FUTURE, **fields(data_quality={"status": "NOT_CHECKED"}))
        self.assertEqual(rec["data_quality"]["status"], "NOT_CHECKED")

    def test_more_variants_than_the_universe_needs_a_deviation(self):
        wide = {"count": 9, "artifact": "x", "sha256": A}
        with self.assertRaises(v2.StatsError):
            v2.record("R1", v2.FUTURE, **fields(variants_tested=wide))
        rec = v2.record("R1", v2.FUTURE, **fields(variants_tested=wide, deviations=[deviation("trial_universe")]))
        self.assertEqual(rec["variants_tested"]["count"], 9)

    def test_record_does_not_share_state_with_its_input(self):
        params = v2.parameters_block({"lookback": 20})
        rec = v2.record("R1", v2.FUTURE, **fields(parameters=params))
        params["values"]["lookback"] = 99
        self.assertEqual(rec["parameters"]["values"]["lookback"], 20)


class Chain(unittest.TestCase):
    def setUp(self):
        self.chain = []
        v2.chain_append(self.chain, v2.record("R1", v2.FUTURE, **fields()), "2025-07-01T00:00Z")

    def test_chain_links_and_verifies(self):
        v2.chain_append(self.chain, v2.record("R2", v2.FUTURE, **fields()), "2025-07-02T00:00Z")
        self.assertEqual(self.chain[1]["prev"], self.chain[0]["hash"])
        self.assertEqual(self.chain[0]["prev"], "0" * 64)
        self.assertTrue(v2.chain_verify(self.chain))

    def test_any_edit_breaks_the_chain(self):
        v2.chain_append(self.chain, v2.record("R2", v2.FUTURE, **fields()), "2025-07-02T00:00Z")
        for mutate in (lambda c: c[0]["record"]["cost_model"].update(round_trip_bps=1.0),
                       lambda c: c[0].update(ts="2020-01-01"), lambda c: c[1].update(prev="d" * 64),
                       lambda c: c.pop(0)):
            broken = copy.deepcopy(self.chain)
            mutate(broken)
            with self.assertRaises(v2.StatsError):
                v2.chain_verify(broken)

    def test_rehashed_rule_break_is_caught_on_replay(self):
        rec = v2.record("R1", v2.FUTURE, **fields(cost_model={"name": "taker", "round_trip_bps": 1.0, "sha256": C}))
        entry = {"seq": 1, "record_id": "R1", "ts": "2025-07-02", "record": rec, "prev": self.chain[0]["hash"]}
        entry["hash"] = factory.sha(entry)
        with self.assertRaises(v2.StatsError):
            v2.chain_verify(self.chain + [entry])

    def test_locked_change_needs_a_deviation_naming_it(self):
        cheap = {"name": "taker", "round_trip_bps": 1.0, "sha256": C}
        with self.assertRaises(v2.StatsError):
            v2.chain_append(self.chain, v2.record("R1", v2.FUTURE, **fields(cost_model=cheap)), "t2")
        with self.assertRaises(v2.StatsError):
            v2.chain_append(self.chain, v2.record("R1", v2.FUTURE, **fields(cost_model=cheap, deviations=[deviation("data_period")])), "t2")
        v2.chain_append(self.chain, v2.record("R1", v2.FUTURE, **fields(cost_model=cheap, deviations=[deviation("cost_model")])), "t2")
        self.assertTrue(v2.chain_verify(self.chain))

    def test_every_locked_field_is_guarded(self):
        changed = {"hypothesis_id": "H2", "lineage": "other",
                   "trial_universe": {"definition": "wider", "size": 50, "members_sha256": A},
                   "parameters": v2.parameters_block({"lookback": 30}), "code_hash": "def5678",
                   "data_source": {"name": "other", "sha256": A},
                   "data_period": {"start": "2024-01-01", "end": "2025-06-30"},
                   "cost_model": {"name": "maker", "round_trip_bps": 12.0, "sha256": C},
                   "evaluation_method": {"name": "other", "sha256": A}}
        self.assertEqual(sorted(changed), sorted(v2.LOCKED))
        for k, value in changed.items():
            with self.assertRaises(v2.StatsError, msg=k):
                v2.chain_append(self.chain, v2.record("R1", v2.FUTURE, **fields(**{k: value})), "t2")

    def test_deviations_only_grow(self):
        two = [deviation("cost_model"), deviation("data_period")]
        chain = []
        v2.chain_append(chain, v2.record("R1", v2.FUTURE, **fields(deviations=two)), "t1")
        for shrunk in ([], two[:1], list(reversed(two))):
            with self.assertRaises(v2.StatsError, msg=str(shrunk)):
                v2.chain_append(chain, v2.record("R1", v2.FUTURE, **fields(deviations=shrunk)), "t2")

    def test_variant_count_never_falls_or_disappears(self):
        fewer = {"count": 4, "artifact": "x", "sha256": A}
        with self.assertRaises(v2.StatsError):
            v2.chain_append(self.chain, v2.record("R1", v2.FUTURE, **fields(variants_tested=fewer)), "t2")
        with self.assertRaises(v2.StatsError):
            v2.chain_append(self.chain, v2.record("R1", v2.FUTURE, **fields(variants_tested=None)), "t2")

    def test_contamination_cannot_be_cleared_silently(self):
        chain = []
        dirty = {"status": "CONTAMINATED", "evidence": EV}
        v2.chain_append(chain, v2.record("R1", v2.FUTURE, **fields(data_quality=dirty)), "t1")
        with self.assertRaises(v2.StatsError):
            v2.chain_append(chain, v2.record("R1", v2.FUTURE, **fields()), "t2")
        v2.chain_append(chain, v2.record("R1", v2.FUTURE, **fields(deviations=[deviation("data_quality")])), "t2")
        self.assertTrue(v2.chain_verify(chain))

    def test_quality_may_improve_from_not_checked(self):
        chain = []
        v2.chain_append(chain, v2.record("R1", v2.FUTURE, **fields(data_quality={"status": "NOT_CHECKED"})), "t1")
        v2.chain_append(chain, v2.record("R1", v2.FUTURE, **fields()), "t2")
        self.assertTrue(v2.chain_verify(chain))

    def test_historical_gap_can_be_documented_later_without_a_deviation(self):
        chain = []
        v2.chain_append(chain, v2.record("OLD", v2.HISTORICAL), "t1")
        v2.chain_append(chain, v2.record("OLD", v2.HISTORICAL, data_source={"name": "x", "sha256": A}), "t2")
        self.assertTrue(v2.chain_verify(chain))
        with self.assertRaises(v2.StatsError):                 # but a documented value does not go back to unknown
            v2.chain_append(chain, v2.record("OLD", v2.HISTORICAL), "t3")

    def test_era_cannot_change(self):
        with self.assertRaises(v2.StatsError):
            v2.chain_append(self.chain, v2.record("R1", v2.HISTORICAL, **fields()), "t2")

    def test_timestamp_and_validity_are_required(self):
        rec = v2.record("R9", v2.FUTURE, **fields())
        with self.assertRaises(v2.StatsError):
            v2.chain_append(self.chain, rec, "")
        rec = dict(rec, lineage="")
        with self.assertRaises(v2.StatsError):
            v2.chain_append(self.chain, rec, "t2")

    def test_jsonl_round_trip_and_tamper(self):
        v2.chain_append(self.chain, v2.record("R2", v2.HISTORICAL), "t2")
        text = v2.render_jsonl(self.chain)
        self.assertEqual(v2.parse_jsonl(text), self.chain)
        self.assertEqual(v2.render_jsonl(v2.parse_jsonl(text)), text)
        with self.assertRaises(v2.StatsError):
            v2.parse_jsonl(text.replace("carry", "other"))

    def test_appending_copies_the_record(self):
        rec = v2.record("R5", v2.HISTORICAL)
        v2.chain_append(self.chain, rec, "t2")
        rec["lineage"] = "changed afterwards"
        self.assertTrue(v2.chain_verify(self.chain))


class Joins(unittest.TestCase):
    def rows(self):
        return [{"seq": 0, "hid": "H1", "lineage": "l", "variants": 3, "hash": "1" * 64},
                {"seq": 1, "hid": "H2", "lineage": "m", "variants": 7, "hash": "2" * 64}]

    def test_historical_view_never_touches_rows_and_invents_nothing(self):
        rows = self.rows()
        before = copy.deepcopy(rows)
        shas = [factory.sha(r) for r in rows]
        chain = []
        v2.chain_append(chain, v2.record("1" * 64, v2.HISTORICAL, lineage="documented-l",
                                         data_source={"name": "x", "sha256": A}), "t1")
        view = v2.historical_view(rows, chain, key="hash")
        self.assertEqual(rows, before)
        self.assertEqual([v["register_row_sha"] for v in view], shas)
        self.assertEqual(view[0]["status"], v2.MISSING_INPUT)   # partly documented is still incomplete
        self.assertEqual(view[0]["fields"]["lineage"], "documented-l")
        self.assertEqual(view[0]["fields"]["parameters"], v2.MISSING_INPUT)
        self.assertEqual(view[1]["status"], v2.MISSING_INPUT)
        self.assertTrue(all(v == v2.MISSING_INPUT for v in view[1]["fields"].values()))
        self.assertEqual(view[1]["fields"]["variants_tested"], v2.MISSING_INPUT)   # the ledger's count is not copied in

    def test_view_shows_the_latest_revision_and_a_complete_record(self):
        chain = []
        v2.chain_append(chain, v2.record("1" * 64, v2.FUTURE, **fields(variants_tested=None)), "t1")
        v2.chain_append(chain, v2.record("1" * 64, v2.FUTURE, **fields()), "t2")
        view = v2.historical_view(self.rows()[:1], chain, key="hash")
        self.assertEqual(view[0]["status"], v2.OK)
        self.assertEqual(view[0]["fields"]["variants_tested"]["count"], 5)

    def test_snapshot_pointer_matches_a_real_snapshot_rendering(self):
        entries = [{"seq": 0, "hid": "H1", "lineage": "l", "variants": 3, "hash": "1" * 64}]
        raw = json.dumps({"ledger": {"entries": entries, "attempts": 1, "variants": 3, "lineages": ["l"],
                                     "alpha_gross": 0.05}}).encode()
        text = snap.render(snap.build(raw))
        ref = {"sha256": v2.snapshot_sha(text), "rules_version": snap.RULES["version"]}
        rec = v2.record("R1", v2.FUTURE, register_snapshot=ref, **fields())
        self.assertEqual(v2.snapshot_matches(rec, text), {"status": v2.OK, "matches": True, "reason": None})
        self.assertEqual(v2.snapshot_matches(rec, text.encode())["matches"], True)
        self.assertFalse(v2.snapshot_matches(rec, text + " ")["matches"])

    def test_no_snapshot_pointer_is_missing_not_false(self):
        rec = v2.record("R1", v2.FUTURE, **fields())
        got = v2.snapshot_matches(rec, "anything")
        self.assertEqual((got["status"], got["matches"]), (v2.MISSING_INPUT, None))

    def test_snapshot_pointer_format(self):
        for ref in ({"sha256": "short", "rules_version": 1}, {"sha256": A}, {"sha256": A, "rules_version": 0}):
            with self.assertRaises(v2.StatsError, msg=str(ref)):
                v2.record("R1", v2.FUTURE, register_snapshot=ref, **fields())

    def test_stats_ref_points_into_a_verified_register_stats_chain(self):
        stats = []
        entry = rs.chain_append(stats, rs.record("S1", sharpe=0.1, provenance=PROV), "t1")
        rec = v2.record("R1", v2.FUTURE, stats_ref={"record_id": "S1", "entry_hash": entry["hash"]}, **fields())
        self.assertTrue(v2.stats_ref_matches(rec, stats)["matches"])
        other = v2.record("R2", v2.FUTURE, stats_ref={"record_id": "S1", "entry_hash": B}, **fields())
        self.assertFalse(v2.stats_ref_matches(other, stats)["matches"])
        self.assertEqual(v2.stats_ref_matches(v2.record("R3", v2.FUTURE, **fields()), stats)["status"], v2.MISSING_INPUT)
        stats[0]["ts"] = "tampered"
        with self.assertRaises(rs.StatsError):
            v2.stats_ref_matches(rec, stats)

    def test_register_stats_records_are_unchanged_by_v2(self):
        rec = rs.record("X1", lineage="carry")
        self.assertEqual(rec, {"schema": rs.SCHEMA, "record_id": "X1", "lineage": "carry"})
        self.assertNotEqual(rs.SCHEMA, v2.SCHEMA)

    def test_validation_inputs_never_invent(self):
        got = v2.validation_inputs(v2.record("OLD", v2.HISTORICAL))
        self.assertEqual(set(got.values()), {None})
        got = v2.validation_inputs(v2.record("R1", v2.FUTURE, **fields()))
        self.assertEqual((got["n_tested"], got["n_preregistered"], got["assumed_cost_bps"], got["declared_data_quality"]),
                         (5, 5, 12.0, "VERIFIED"))

    def test_module_opens_no_file_and_writes_no_ledger(self):
        with open(SOURCE, encoding="utf-8") as f:
            src = f.read()
        for bad in ("open(", "sqlite3", "socket", "urllib", "Ledger("):
            self.assertNotIn(bad, src, bad)


if __name__ == "__main__":
    import direct_guard  # noqa: E402,F401  (order 75: quarantine guard for direct runs)
    unittest.main()
