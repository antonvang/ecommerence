"""Director order 51 P0: EVALUATOR_SPEC v1.1 rules and closed-form references (the 'third simple mathematical
reference'), synthetic only."""
import copy
import json
import math
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from research.desk.crosscheck import claude_eval_v11 as ev  # noqa: E402

H = 3600
T0 = 1_800_000_000 - (1_800_000_000 % H)


def fixture(rets, signal=1.0, cost=0.0, rule="sign", n_assets=1, extra_h=None, ledger=None):
    obs = []
    for k, r in enumerate(rets):
        for j in range(n_assets):
            obs.append({"ts": T0 + k * H, "asset": f"A{j}", "ret": r, "funding": 0.0,
                        "signals": {"s": {"value": signal if not callable(signal) else signal(k), "avail_ts": T0}}})
    hyps = [{"hid": "H1", "family": "f", "signal_key": "s", "rule": rule, "cost_bps": cost, "funding": False}]
    return {"fixture_id": "X", "cadence_s": H, "alpha": 0.05, "q_fdr": 0.1,
            "window": {"start": T0, "end": T0 + len(rets) * H},
            "universe": {f"A{j}": {"listed_from": T0, "delisted_at": None} for j in range(n_assets)},
            "hypotheses": hyps + (extra_h or []), "observations": obs, "ledger_requests": ledger or []}


class ClosedForm(unittest.TestCase):
    def test_alternating_series_hac_t_is_exactly_three(self):
        # x_t = c + (-1)^t a, T = 30 -> L = 3, S = a^2/30, se = a/30, t = 30 c / a = 3
        c, a = 0.001, 0.01
        r = ev.evaluate(fixture([c + (a if k % 2 == 0 else -a) for k in range(30)]))["hypotheses"]["H1"]
        self.assertEqual((r["status"], r["hac_lag"]), ("TESTED", 3))
        self.assertAlmostEqual(r["se"], a / 30, places=15)
        self.assertAlmostEqual(r["t"], 3.0, places=10)
        self.assertAlmostEqual(r["p_one"], 0.5 * math.erfc(3 / math.sqrt(2)), places=12)

    def test_flip_every_bar_costs(self):
        # sign flips each bar: |dw| = 1 at the first bar, 2 afterwards; cost 10 bp -> total 0.001 + 0.002 * 39
        r = ev.evaluate(fixture([0.0] * 40, signal=lambda k: 1.0 if k % 2 == 0 else -1.0, cost=10.0))
        self.assertAlmostEqual(r["hypotheses"]["H1"]["total_cost"], 0.001 + 0.002 * 39, places=15)
        self.assertAlmostEqual(r["hypotheses"]["H1"]["mean_net"], -(0.001 + 0.002 * 39) / 40, places=15)

    def test_constant_series_keeps_lag_but_no_test(self):
        r = ev.evaluate(fixture([0.002] * 40))["hypotheses"]["H1"]
        self.assertEqual((r["status"], r["hac_lag"], r["se"], r["t"]), ("INSUFFICIENT", 3, None, None))


class Validation(unittest.TestCase):
    def codes(self, fx):
        r = ev.evaluate(fx)
        self.assertEqual(r["status"], "INVALID_INPUT")
        self.assertNotIn("hypotheses", r)
        return {(e["code"], e["path"]) for e in r["errors"]}

    def test_unknown_cost_component_and_negative_cost(self):
        fx = fixture([0.0] * 40)
        fx["hypotheses"][0]["fee_bps"] = 3.0
        self.assertIn(("UNKNOWN_FIELD", "hypotheses[0].fee_bps"), self.codes(fx))
        fx = fixture([0.0] * 40, cost=-1.0)
        self.assertIn(("BAD_VALUE", "hypotheses[0].cost_bps"), self.codes(fx))

    def test_bad_times_strings_floats_and_order(self):
        fx = fixture([0.0] * 40)
        fx["observations"][3]["ts"] = "2027-01-15T08:00:00+01:00"
        fx["observations"][4]["ts"] = float(fx["observations"][4]["ts"])
        fx["window"]["end"] = fx["window"]["start"]
        c = self.codes(fx)
        self.assertTrue({("BAD_TIME", "observations[3].ts"), ("BAD_TIME", "observations[4].ts"),
                         ("BAD_VALUE", "window")} <= c)

    def test_types_duplicates_unknown_signal_missing(self):
        fx = fixture([0.0] * 40, extra_h=[{"hid": "H1", "family": "g", "signal_key": "zz", "rule": "sign",
                                           "cost_bps": 1.0, "funding": False}])
        fx["observations"][0]["ret"] = "nan"
        fx["observations"][1]["ret"] = True
        del fx["observations"][2]["funding"]
        c = self.codes(fx)
        self.assertTrue({("DUPLICATE_HID", "hypotheses[1].hid"), ("UNKNOWN_SIGNAL", "hypotheses[1].signal_key"),
                         ("BAD_TYPE", "observations[0].ret"), ("BAD_TYPE", "observations[1].ret"),
                         ("MISSING_FIELD", "observations[2].funding")} <= c)

    def test_lock_detects_changed_data_or_protocol(self):
        fx = fixture([0.001] * 40)
        proto = {k: fx[k] for k in ("cadence_s", "window", "universe", "hypotheses", "alpha", "q_fdr")}
        fx["lock"] = {"protocol_sha256": ev.sha(proto), "data_sha256": ev.sha(fx["observations"])}
        self.assertEqual(ev.evaluate(fx)["status"], "OK")
        g = copy.deepcopy(fx)
        g["observations"][5]["ret"] = 0.5
        self.assertEqual(self.codes(g), {("LOCK_MISMATCH", "lock.data_sha256")})
        g = copy.deepcopy(fx)
        g["hypotheses"][0]["cost_bps"] = 1.0
        self.assertEqual(self.codes(g), {("LOCK_MISMATCH", "lock.protocol_sha256")})


class Rules(unittest.TestCase):
    def test_embargo(self):
        fx = fixture([0.01] * 40)
        fx["window"]["embargo_s"] = 5 * H
        r = ev.evaluate(fx)["hypotheses"]["H1"]
        self.assertEqual((r["n_embargo"], r["T"]), (5, 35))

    def test_key_conflict_blocks_double_alpha(self):
        led = [{"key": "k", "hid": "H1", "family": "f", "variants": 1, "alpha": 0.0125, "ts": T0},
               {"key": "k", "hid": "H1", "family": "f", "variants": 1, "alpha": 0.0125, "ts": T0 + 99},
               {"key": "k", "hid": "H1", "family": "f", "variants": 1, "alpha": 0.025, "ts": T0 + 100}]
        L = ev.evaluate(fixture([0.0] * 40, ledger=led))["ledger"]
        self.assertEqual((L["entries"], L["idempotent_hits"], L["errors"]),
                         (1, 1, [{"key": "k", "reason": "key_conflict"}]))
        self.assertEqual(L["totals"]["f"]["alpha"], 0.0125)

    def test_short_duplicate_and_atomic_output(self):
        fx = fixture([0.001] * 10, extra_h=[{"hid": "H2", "family": "f", "signal_key": "s", "rule": "sign",
                                             "cost_bps": 9.0, "funding": False}])
        r = ev.evaluate(fx)["hypotheses"]["H2"]
        self.assertEqual((r["status"], r["duplicate_of"], r["t"]), ("DUPLICATE", "H1", None))
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "fx.json")
            with open(p, "w", encoding="utf-8") as f:
                json.dump(fx, f)
            with open(os.path.join(d, "X.json"), "w", encoding="utf-8") as f:
                f.write('{"partial":')                                   # interrupted earlier run
            ev.main([p, "--out", d])
            ev.main([p, "--out", d])
            with open(os.path.join(d, "X.json"), encoding="utf-8") as f:
                self.assertEqual(json.load(f)["status"], "OK")
            self.assertEqual(sorted(os.listdir(d)), ["X.json", "fx.json"])


if __name__ == "__main__":
    unittest.main()
