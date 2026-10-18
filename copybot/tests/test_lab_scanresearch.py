"""Non-decisional research jobs from the scans (research/PROTOCOL_V3.md amendment 9 section 3): the daily scan digest
and the dossier of a new INVESTIGATE key, run by report-1, plus the Danish feed texts."""
import hashlib
import json
import os
import shutil
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lab import command, diagnose, fleet, jobs, lifecycle, pipeline, scanner  # noqa: E402
from lab import scanresearch as sr  # noqa: E402
from lab.db import DB  # noqa: E402
from lab.engine import catalogue  # noqa: E402
from tests.test_lab_s3 import World  # noqa: E402

DAY, HOUR = 86400, 3600
D = 20000 * DAY                                    # 2024-10-04 00:00 UTC, long over
DAY_S = time.strftime("%Y-%m-%d", time.gmtime(D))
PC, VS = "pricing_constraint/2", "venue_subsidy/1"
FORMAL = ("experiments", "transitions", "results", "trials", "approvals", "alpha_ledger", "observations", "datasets",
          "sim_orders", "sim_fills", "sim_cancels", "sim_equity", "risk_events")


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="labscan")
        self.path = os.path.join(self.tmp, "lab.db")
        self.db = DB(self.path)
        self.p = mock.patch.object(pipeline, "ARTIFACTS", os.path.join(self.tmp, "artifacts"))
        self.p.start()

    def tearDown(self):
        self.p.stop()
        self.db.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def ob(self, ts, metric, inst, value=None, threshold=None, flagged=0, det=PC, db=None):
        (db or self.db).append("observations", ts=ts, detector=det, source="unit", instrument=inst, metric=metric,
                               value=value, threshold=threshold, flagged=flagged, payload={})

    def scans(self, hours, base=D, db=None):
        for h in hours:                                    # the detector ran in these clock hours
            self.ob(base + h * HOUR, "coins_compared", "hyperliquid_binance_perps", 10, db=db)

    def events(self, kind):
        return [json.loads(r[0]) for r in self.db.q("SELECT payload FROM events WHERE kind=? ORDER BY id", kind)]

    def counts(self):
        return {t: self.db.one(f"SELECT COUNT(*) FROM {t}")[0] for t in FORMAL}

    def key(self, out, metric, inst, det=PC):
        return next(x for x in out["keys"] if (x["detector"], x["metric"], x["instrument"]) == (det, metric, inst))


class Digest(Base):
    def test_rule_boundaries(self):
        at = sr.COST_MULT * sr.COST_REF                                           # exactly the cost condition
        self.scans(range(24))
        for h in range(6):
            self.ob(D + h * HOUR, "cross_venue_gap", "AAA", at, 0.003, 1)          # 6 hours, at the cost boundary
            self.ob(D + h * HOUR, "cross_venue_gap", "CCC", -at * 0.99, 0.003, 1)  # 6 hours, just below it
            self.ob(D + h * 60, "perp_premium", "GGG", 0.02, 0.005, 1)            # 6 flags in one clock hour
        for h in range(5):
            self.ob(D + h * HOUR, "cross_venue_gap", "BBB", 0.01, 0.003, 1)        # 5 hours only
        for h in range(24):
            self.ob(D + h * HOUR, "median_gross_yield_day", "polymarket_reward_markets", 0.02, 0.005, 1, det=VS)
        self.ob(D - HOUR, "cross_venue_gap", "OLD", 0.01, 0.003, 1)               # the day before: 7 d only
        self.ob(D + DAY, "cross_venue_gap", "NEXT", 0.01, 0.003, 1)               # the next day: not in this digest
        out = sr.digest(self.db, DAY_S)
        got = {(x["metric"], x["instrument"]): (x["decision"], x["why"]) for x in out["keys"]}
        self.assertEqual(got[("cross_venue_gap", "AAA")][0], "INVESTIGATE")
        self.assertIn("4.00x the cost reference (>= 4x)", got[("cross_venue_gap", "AAA")][1])
        self.assertEqual(got[("cross_venue_gap", "CCC")],
                         ("NO_ACTION", "persistent (6 clock hours in 24 h) but the median |value| is 3.96x the cost "
                                       "reference, below 4x"))
        self.assertEqual(got[("cross_venue_gap", "BBB")],
                         ("NO_ACTION", "not persistent: flagged in 5 of the required 6 distinct clock hours in 24 h"))
        self.assertEqual(got[("perp_premium", "GGG")][0], "NO_ACTION")
        self.assertIn("flagged in 1 of the required 6", got[("perp_premium", "GGG")][1])
        self.assertEqual(got[("median_gross_yield_day", "polymarket_reward_markets")][0], "NO_ACTION")
        self.assertIn("no trading-cost reference", got[("median_gross_yield_day", "polymarket_reward_markets")][1])
        self.assertEqual(got[("coins_compared", "hyperliquid_binance_perps")],
                         ("NO_ACTION", "never flagged in the 24 h"))
        self.assertEqual(got[("cross_venue_gap", "OLD")], ("NO_ACTION", "not observed in the 24 h"))
        self.assertNotIn(("cross_venue_gap", "NEXT"), got)
        self.assertEqual(out["summary"]["investigate"], 1)
        self.assertFalse(out["decisional"])
        self.assertEqual(out["windows"], {"24h": [D, D + DAY], "7d": [D + DAY - 7 * DAY, D + DAY]})

    def test_units_against_the_cost_reference(self):
        c = catalogue.COSTS
        self.assertEqual(sr.COST_REF, c["taker_fee"] + c["half_spread"] + c["slippage"])
        self.assertAlmostEqual(sr.COST_REF, 0.0009)                             # 0.09 % of notional per taker fill
        self.scans(range(10))
        for h, v in enumerate((0.0045, -0.0045, 0.0045)):                       # a gap is a fraction of price
            self.ob(D + h * HOUR, "cross_venue_gap", "ETH", v, 0.003, 1)
        for h, k in enumerate((1, 2, 3, 4, 5)):
            self.ob(D + h * HOUR, "perp_premium", "SOLUSDT", -0.005 * k, 0.005, 1)
        self.ob(D, "negrisk_locked_profit", "who-wins", 12.0, 5.0, 1)
        out = sr.digest(self.db, DAY_S)
        gap = self.key(out, "cross_venue_gap", "ETH")
        self.assertEqual((gap["24h"]["median_abs_value"], gap["24h"]["vs_cost_reference"]), (0.0045, 5.0))
        self.assertEqual(gap["24h"]["size_vs_threshold"]["median"], 1.5)        # 0.45 % against the 0.30 % threshold
        self.assertEqual(gap["cost_reference"], sr.COST_REF)
        prem = self.key(out, "perp_premium", "SOLUSDT")
        self.assertEqual(prem["24h"]["size_vs_threshold"], {"median": 3.0, "p90": 4.6})   # linear interpolation
        self.assertEqual(prem["24h"]["median_abs_value"], 0.015)                # |negative premium|
        self.assertEqual(prem["24h"]["vs_cost_reference"], round(0.015 / sr.COST_REF, 6))
        neg = self.key(out, "negrisk_locked_profit", "who-wins")
        self.assertIsNone(neg["cost_reference"])
        self.assertIn("USD", neg["cost_note"])
        self.assertNotIn("vs_cost_reference", neg["24h"])
        self.assertEqual(out["rules"]["cost_reference"], sr.COST_REF)

    def test_persistence_error_rate_and_windows(self):
        self.scans(range(10))
        for h in (2, 3):
            self.ob(D + h * HOUR, "error", "hyperliquid_binance_perps")           # 2 of 10 scans failed
        for h in (0, 1, 2, 5):
            self.ob(D + h * HOUR, "cross_venue_gap", "ETH", 0.004, 0.003, 1)
        self.ob(D - 3 * DAY, "cross_venue_gap", "ETH", 0.004, 0.003, 1)          # in the 7 d
        self.ob(D - 8 * DAY, "cross_venue_gap", "ETH", 0.004, 0.003, 1)          # outside the 7 d
        k = self.key(sr.digest(self.db, DAY_S), "cross_venue_gap", "ETH")
        s = k["24h"]
        self.assertEqual((s["observations"], s["flagged"], s["flagged_clock_hours"], s["scanned_clock_hours"]),
                         (4, 4, 4, 10))
        self.assertEqual((s["persistence"], s["longest_flagged_run_h"], s["detector_error_rate"]), (0.4, 3, 0.2))
        self.assertEqual((k["7d"]["flagged"], k["7d"]["flagged_clock_hours"]), (5, 5))
        self.assertNotIn(("error", "hyperliquid_binance_perps"),
                         {(x["metric"], x["instrument"]) for x in sr.digest(self.db, DAY_S)["keys"]})

    def test_digest_is_deterministic_and_independent_of_insertion_order(self):
        rows = [(D + h * HOUR, "cross_venue_gap", f"C{h % 3}", 0.003 + h * 1e-4, 0.003, 1) for h in range(20)]
        rows += [(D + h * HOUR, "coins_compared", "hyperliquid_binance_perps", 10, None, 0) for h in range(24)]
        other = DB(os.path.join(self.tmp, "other.db"))
        try:
            for r in rows:
                self.ob(*r)
            for r in reversed(rows):
                self.ob(*r, db=other)
            job = {"job_id": f"scan_digest|{DAY_S}", "payload": {"day": DAY_S}}
            a = sr.step_digest(self.db, job, "report-1")["artifact"]
            self.assertTrue(a["path"].endswith(f"artifacts/_diagnostic/scanner/{DAY_S}.json"), a)
            with open(os.path.join(pipeline.ARTIFACTS, "_diagnostic", "scanner", f"{DAY_S}.json"), "rb") as f:
                first = f.read()
            self.assertEqual(sr.step_digest(self.db, job, "report-1")["artifact"]["sha256"], a["sha256"])
            with mock.patch.object(pipeline, "ARTIFACTS", os.path.join(self.tmp, "artifacts2")):
                b = sr.step_digest(other, job, "report-1")["artifact"]
                with open(os.path.join(self.tmp, "artifacts2", "_diagnostic", "scanner", f"{DAY_S}.json"), "rb") as f:
                    second = f.read()
            self.assertEqual((b["sha256"], second), (a["sha256"], first))
            self.assertEqual(hashlib.sha256(first).hexdigest(), a["sha256"])
            ev = self.events("research.digest")[-1]
            self.assertEqual((ev["day"], ev["artifact_sha256"], ev["decisional"]), (DAY_S, a["sha256"], False))
            self.assertEqual(ev["decisions"][f"{PC}|cross_venue_gap|C0"][0], "INVESTIGATE")
        finally:
            other.close()

    def test_a_day_that_is_not_over_is_refused(self):
        today = time.strftime("%Y-%m-%d", time.gmtime(time.time()))
        with self.assertRaises(pipeline.StepError):
            sr.step_digest(self.db, {"payload": {"day": today}}, "report-1")
        with self.assertRaises(pipeline.StepError):
            sr.step_digest(self.db, {"payload": {"day": "yesterday"}, "job_id": "scan_digest|x"}, "report-1")
        self.assertEqual(self.events("research.digest"), [])


class Queue(Base):
    def test_one_digest_per_day_from_00_30_utc(self):
        end = D + DAY
        self.ob(D + HOUR, "coins_compared", "hyperliquid_binance_perps", 10)
        self.assertEqual(sr.enqueue(self.db, now=end + sr.DIGEST_DELAY_S - 1), 0)          # 00:29:59: not yet
        self.assertIsNone(jobs.get(self.db, f"scan_digest|{DAY_S}"))
        self.assertEqual(sr.enqueue(self.db, now=end + sr.DIGEST_DELAY_S), 1)              # 00:30
        j = jobs.get(self.db, f"scan_digest|{DAY_S}")
        self.assertEqual((j["kind"], j["exp_id"], j["priority"], j["max_attempts"], j["timeout_s"], j["next_run"],
                          j["payload"]), ("scan_digest", None, 60, 2, 120, end + sr.DIGEST_DELAY_S, {"day": DAY_S}))
        self.assertEqual(sr.enqueue(self.db, now=end + 5 * HOUR), 0)                       # one job per day
        self.assertEqual(sr.enqueue(self.db, now=end + DAY + sr.DIGEST_DELAY_S), 0)        # no scans that day
        self.ob(end + HOUR, "coins_compared", "hyperliquid_binance_perps", 10)
        self.assertEqual(sr.enqueue(self.db, now=end + DAY + sr.DIGEST_DELAY_S), 1)
        self.assertEqual(jobs.counts(self.db)["queued"], 2)
        self.assertNotIn("scan_digest", fleet.HEAVY)
        self.assertNotIn("scan_dossier", fleet.HEAVY)

    def test_one_dossier_per_new_investigate_key(self):
        k1 = {"detector": PC, "metric": "cross_venue_gap", "instrument": "hyperliquid_binance_perps"}
        k2 = {"detector": PC, "metric": "perp_premium", "instrument": "binance_perps"}
        k3 = {"detector": VS, "metric": "median_gross_yield_day", "instrument": "polymarket_reward_markets"}
        first = self.db.event("market.event", scanner.ACTOR, "C_a", {"key": k1, "decision": "INVESTIGATE",
                                                                     "why": "new candidate C_a", "scan_ts": D + HOUR})
        self.db.event("market.event", scanner.ACTOR, "C_a", {"key": dict(reversed(list(k1.items()))),
                                                             "decision": "INVESTIGATE", "scan_ts": D + 9 * HOUR})
        self.db.event("market.event", scanner.ACTOR, "C_b", {"key": k2, "decision": "INVESTIGATE", "scan_ts": D})
        self.db.event("market.event", scanner.ACTOR, "X01", {"key": k3, "decision": "NO_ACTION", "scan_ts": D})
        self.assertEqual(sr.enqueue(self.db, now=D), 2)
        self.assertEqual(sr.enqueue(self.db, now=D), 0)                                    # one job per key
        sha = hashlib.sha1(json.dumps(k1, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        self.assertEqual(sr.key_id(k1), sha)
        j = jobs.get(self.db, f"scan_dossier|{sha}")
        self.assertEqual((j["kind"], j["exp_id"], j["priority"], j["max_attempts"], j["timeout_s"]),
                         ("scan_dossier", None, 60, 2, 120))
        self.assertEqual(j["payload"], {"key": k1, "exp_id": "C_a", "event_id": first, "scan_ts": D + HOUR})
        self.assertIsNotNone(jobs.get(self.db, f"scan_dossier|{sr.key_id(k2)}"))
        self.assertIsNone(jobs.get(self.db, f"scan_dossier|{sr.key_id(k3)}"))

    def test_scan_jobs_never_move_an_experiment_on_the_orbit(self):
        for kind in ("scan_digest", "scan_dossier"):
            jobs.enqueue(self.db, f"{kind}|x", kind, "E_a", {}, actor="system:t")
        self.assertEqual(command.job_state(self.db, "E_a"), (None, None, None))
        self.assertTrue({"scan_digest", "scan_dossier"} <= set(pipeline.HANDLERS))
        kinds = {n: k for n, _r, k, *_ in fleet.ROSTER}
        self.assertEqual(kinds["report-1"], ("report", "diagnose", "scan_digest", "scan_dossier"))


class Dossier(Base):
    KEY = {"detector": PC, "metric": "cross_venue_gap", "instrument": "hyperliquid_binance_perps"}

    def candidate(self, eid, state="DISCOVERED", mech="cross_venue_perp_gap"):
        self.db.append("experiments", exp_id=eid, version=1, created_ts=0, mechanism_tag=mech, fingerprint=eid,
                       spec_json={"execution": "taker_two_venues"})
        self.db.append("transitions", exp_id=eid, ts=0, from_state=None, to_state=state, actor="fixture",
                       reason="fixture")

    def flags(self, hours, value=0.006, inst="ETH"):
        self.scans(range(24))
        for h in hours:
            self.ob(D + h * HOUR, "cross_venue_gap", inst, value, 0.003, 1)

    def test_recommendation_follows_registry_and_persistence(self):
        self.flags(range(8))
        self.candidate("C_new")
        d = sr.dossier(self.db, self.KEY, "C_new", D + 7 * HOUR)
        self.assertEqual((d["scope"][:6], d["instruments_flagged_7d"], d["24h"]["flagged_clock_hours"]),
                         ("family", ["ETH"], 8))
        self.assertEqual((d["rule_decision"], d["advice"], d["registry"]["state"]), ("INVESTIGATE", "family_draft",
                                                                                     "DISCOVERED"))
        self.assertIn("needs the user's approval", d["recommendation"])
        self.assertIn("Non-decisional", d["recommendation"])
        early = sr.dossier(self.db, self.KEY, "C_new", D + HOUR)                  # anchored at the deciding scan
        self.assertEqual((early["24h"]["flagged_clock_hours"], early["advice"]), (2, "observe"))
        self.candidate("X_live", state="EXTERNAL")                                # same mechanism and execution
        self.assertEqual(sr.dossier(self.db, self.KEY, "C_new", D + 7 * HOUR)["advice"], "covered")
        self.candidate("C_old", state="SUPPRESSED", mech="other")
        g = sr.dossier(self.db, self.KEY, "C_old", D + 7 * HOUR)
        self.assertEqual(g["advice"], "graveyard")
        eth = {"detector": PC, "metric": "cross_venue_gap", "instrument": "ETH"}
        inst = sr.dossier(self.db, eth, None, D + 7 * HOUR)
        self.assertEqual((inst["scope"], inst["registry"]["state"]), ("instrument", None))

    def test_dossier_job_writes_only_its_artifact_and_event(self):
        self.flags(range(3))
        self.candidate("C_new")
        before = self.counts()
        p = {"key": self.KEY, "exp_id": "C_new", "event_id": 7, "scan_ts": D + 2 * HOUR}
        r = sr.step_dossier(self.db, {"payload": p}, "report-1")
        path = os.path.join(pipeline.ARTIFACTS, "_diagnostic", "scanner", f"dossier_{sr.key_id(self.KEY)}.json")
        with open(path, "rb") as f:
            self.assertEqual(hashlib.sha256(f.read()).hexdigest(), r["artifact"]["sha256"])
        ev = self.db.one("SELECT exp_id, payload FROM events WHERE kind='research.dossier'")
        self.assertEqual(ev["exp_id"], "C_new")
        self.assertEqual(json.loads(ev["payload"])["advice"], "observe")
        self.assertEqual(self.counts(), before)
        self.assertEqual(lifecycle.state(self.db, "C_new"), "DISCOVERED")
        with self.assertRaises(pipeline.StepError):
            sr.step_dossier(self.db, {"payload": {"key": self.KEY}}, "report-1")


class EndToEnd(Base):
    def test_report_agent_runs_digest_and_dossier_without_touching_formal_tables_or_the_network(self):
        d = (int(time.time()) - sr.DIGEST_DELAY_S) // DAY * DAY - DAY            # the last day whose digest is due
        day = time.strftime("%Y-%m-%d", time.gmtime(d))
        w = World(gap=0.006)
        for h in range(8):
            scanner.run(self.db, ["pricing_constraint"], w.get, w.post, now=d + h * HOUR + 60)
        inv = self.db.q("SELECT exp_id, payload FROM events WHERE kind='market.event' AND "
                        "json_extract(payload, '$.decision')='INVESTIGATE'")
        self.assertEqual(len(inv), 1)
        cand, key = inv[0]["exp_id"], json.loads(inv[0]["payload"])["key"]
        before = self.counts()
        self.assertEqual(fleet.strategy_pass(self.db)["scan_research_queued"], 2)
        self.assertEqual(fleet.strategy_pass(self.db)["scan_research_queued"], 0)
        agent = [a for a in fleet.agents(self.path) if a.name == "report-1"][0]
        with mock.patch.object(fleet, "PROCESSES", False), \
                mock.patch("socket.socket", side_effect=AssertionError("network used")), \
                mock.patch("urllib.request.urlopen", side_effect=AssertionError("network used")):
            agent(self.db)
            agent(self.db)
        dj, sj = jobs.get(self.db, f"scan_digest|{day}"), jobs.get(self.db, f"scan_dossier|{sr.key_id(key)}")
        self.assertEqual((dj["status"], sj["status"]), ("done", "done"), (dj, sj))
        dg = self.events("research.digest")[0]
        self.assertEqual(dg["investigate"], [f"{PC}|cross_venue_gap|ETH"])          # 8 h, 0.6 % = 6.7x the costs
        self.assertEqual(dg["decisions"][f"{PC}|identity_mismatch_suspected|PIX"][0], "NO_ACTION")
        done = {e["job_id"]: e for e in self.events("job.done")}
        self.assertEqual(done[f"scan_digest|{day}"]["artifact_sha256"], dg["artifact_sha256"])
        with open(os.path.join(pipeline.ARTIFACTS, "_diagnostic", "scanner", f"{day}.json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f)["summary"]["investigate"], 1)
        ds = self.db.one("SELECT exp_id, payload FROM events WHERE kind='research.dossier'")
        p = json.loads(ds["payload"])
        self.assertEqual((ds["exp_id"], p["advice"], p["registry_state"]), (cand, "observe", "DISCOVERED"))
        self.assertEqual(done[f"scan_dossier|{sr.key_id(key)}"]["artifact_sha256"], p["artifact_sha256"])
        self.assertEqual(self.counts(), before)                                   # nothing formal written
        self.assertEqual(lifecycle.state(self.db, cand), "DISCOVERED")
        self.assertEqual(command.job_state(self.db, cand), (None, None, None))     # never on the orbit
        self.assertEqual(self.db.one("SELECT COUNT(*) FROM jobs WHERE exp_id IS NOT NULL")[0], 0)
        self.assertEqual(command.research_progress(self.db)["runnable_jobs"], 0)
        items = command.feed(self.db)["items"]
        self.assertEqual([i["tag"] for i in items[:2]], ["SØGNING", "UNDERSØG"])   # dossier only says observe
        self.assertTrue(items[0]["text"].startswith("Dossier: prisforskel Hyperliquid/Binance"))
        self.assertTrue(items[1]["text"].startswith(f"Døgnoverblik over søgningen {day}: "))


class FeedDanish(Base):
    WHYS = (("waiting for persistence: flagged in 1 of the required 2 clock hours within 24 h",
             "venter på vedvarenhed: markeret i 1 af de krævede 2 klokketimer inden for 24 timer"),
            ("graveyard: C_0755f34d6d is SUPPRESSED", "kirkegård: C_0755f34d6d er sorteret fra"),
            ("graveyard match L22_m3: suppressed as C_ab", "kirkegård: matcher L22_m3, sorteret fra som C_ab"),
            ("already registered: C_ce89a47faa is DISCOVERED", "allerede registreret: C_ce89a47faa er opdaget"),
            ("covered by active experiment X01_pm_lp_v1", "dækket af aktivt eksperiment X01_pm_lp_v1"),
            ("new candidate C_x; a test needs a pre-registered forward template",
             "ny kandidat C_x; en test kræver en forhåndsregistreret fremadtest-skabelon"),
            ("data source failed: OSError('binance unreachable')", "datakilde fejlede: OSError('binance unreachable')"),
            ("data source failed: detector failed: RuntimeError('format')",
             "datakilde fejlede: detektor fejlede: RuntimeError('format')"))

    def test_market_event_reasons_in_danish_and_the_stored_events_unchanged(self):
        key = {"detector": PC, "metric": "perp_premium", "instrument": "binance_perps"}
        for en, _ in self.WHYS:
            self.db.event("market.event", scanner.ACTOR, None, {"key": key, "decision": "NO_ACTION", "why": en})
        stored = [r[0] for r in self.db.q("SELECT payload FROM events WHERE kind='market.event' ORDER BY id")]
        items = list(reversed(command.feed(self.db)["items"]))
        self.assertEqual([i["text"] for i in items], [f"Marked: perp-præmie mod indeks binance_perps - {da}"
                                                      for _, da in self.WHYS])
        self.assertEqual([r[0] for r in self.db.q("SELECT payload FROM events WHERE kind='market.event' ORDER BY id")],
                         stored)
        self.assertEqual([json.loads(s)["why"] for s in stored], [en for en, _ in self.WHYS])

    def test_lessons_in_danish_with_their_numbers(self):
        s = diagnose.series([0.01] * 3 + [0.0] * 37 + [-0.0001] * 40 + [0.0] * 40)
        ls, _ = diagnose.lessons(s, {"net Sharpe > buy-and-hold": False})
        ls += diagnose.lessons(diagnose.series([0.001] * 10 + [0.0] * 40), {})[0][1:]
        ls += diagnose.lessons(diagnose.series([-0.001] * 50), {"deflated Sharpe probability >= 0.95": False})[0]
        ls += diagnose.lessons(diagnose.series([0.001, -0.0005] * 30), {})[0]
        ls += diagnose.lessons({"n": 0}, {})[0]
        self.assertEqual([sr.lesson_da(x) for x in ls], [
            "ustabil: positiv i færre end 2 af 3 tidsmæssige tredjedele",
            "koncentreret: de 5 bedste dage står for 100% af det positive nettoafkast",
            "slået af køb-og-hold i samme periode",
            "sjældent aktiv: nettoafkast forskelligt fra 0 på kun 20% af dagene (lille effektiv stikprøve)",
            "ingen fordel: nettoafkastet i alt er <= 0 i valideringen",
            "fejlede kun held-tjekket (mange forsøg)",
            "ingen enkelt svaghed fundet af disse regler",
            "ingen registreret valideringsserie"])
        self.db.event("research.diagnostic", "system:report-1", "E_a", {"lessons": ls[:2]})
        item = command.feed(self.db)["items"][0]
        self.assertEqual((item["tag"], item["text"]), ("LÆRDOM", "E_a: ustabil: positiv i færre end 2 af 3 tidsmæssige "
                                                                 "tredjedele; koncentreret: de 5 bedste dage står for "
                                                                 "100% af det positive nettoafkast"))

    def test_digest_and_dossier_feed_texts(self):
        self.db.event("research.digest", "system:report-1", None, {"day": "2026-10-18", "keys": 0, "investigate": []})
        self.db.event("research.digest", "system:report-1", None,
                      {"day": "2026-10-18", "keys": 5, "investigate": [f"{PC}|perp_premium|BRUSDT"],
                       "artifact_sha256": "ab"})
        self.db.event("research.dossier", "system:report-1", "C_x",
                      {"key": Dossier.KEY, "advice": "observe", "recommendation": "keep observing: ..."})
        dos, dig, quiet = command.feed(self.db)["items"][:3]
        self.assertEqual((dos["tag"], dos["text"], dos["detail"]),
                         ("SØGNING", "Dossier: prisforskel Hyperliquid/Binance hyperliquid_binance_perps - endnu ikke "
                                      "vedvarende over omkostningerne: måles videre i døgnoverblikket (afgør intet)",
                          "keep observing: ..."))
        self.assertEqual((dig["tag"], dig["text"]),
                         ("UNDERSØG", "Døgnoverblik over søgningen 2026-10-18: 5 målte serier i døgnet · 1 undersøges "
                                      "(perp-præmie mod indeks BRUSDT) · 4 ingen handling (afgør intet)"))
        self.assertEqual(quiet["tag"], "SØGNING")


class VerifierFindings(Base):
    """Findings of the adversarial review of the scan research jobs (2026-10-19)."""
    KEY = {"detector": PC, "metric": "cross_venue_gap", "instrument": "hyperliquid_binance_perps"}

    def test_a_family_dossier_judges_each_instrument_on_its_own(self):
        self.scans(range(24))
        for h, coin in enumerate("ABCDEF"):                        # six coins, one flagged hour each
            self.ob(D + h * HOUR, "cross_venue_gap", coin, 0.006, 0.003, 1)
        d = sr.dossier(self.db, self.KEY, None, D + 6 * HOUR)
        self.assertEqual(d["24h"]["flagged_clock_hours"], 6)         # pooled: looks persistent
        self.assertEqual((d["rule_decision"], d["instruments_meeting_rule"]), ("NO_ACTION", []))
        self.assertIn("no single instrument", d["rule_why"])
        for h in range(6, 12):                                        # ETH alone persists for 6 hours
            self.ob(D + h * HOUR, "cross_venue_gap", "ETH", 0.006, 0.003, 1)
        d = sr.dossier(self.db, self.KEY, None, D + 12 * HOUR)
        self.assertEqual((d["rule_decision"], d["instruments_meeting_rule"]), ("INVESTIGATE", ["ETH"]))

    def test_missing_days_are_backfilled(self):
        self.ob(D + HOUR, "coins_compared", "hyperliquid_binance_perps", 10)
        self.ob(D + DAY + HOUR, "coins_compared", "hyperliquid_binance_perps", 10)
        self.assertEqual(sr.enqueue(self.db, now=D + 3 * DAY + sr.DIGEST_DELAY_S), 2)   # the fleet was down 2 days
        self.assertIsNotNone(jobs.get(self.db, f"scan_digest|{DAY_S}"))
        self.assertEqual(sr.enqueue(self.db, now=D + 3 * DAY + sr.DIGEST_DELAY_S), 0)

    def test_the_digest_counts_only_series_measured_that_day(self):
        self.ob(D - 3 * DAY, "perp_premium", "SOLUSDT", 0.004, 0.005, 0)           # inside the 7 d, not the day
        self.ob(D + HOUR, "cross_venue_gap", "ETH", 0.001, 0.003, 0)
        out = sr.digest(self.db, DAY_S)
        self.assertEqual((out["summary"]["keys"], out["summary"]["keys_24h"]), (2, 1))
        self.assertIn("1 målte serier i døgnet", sr.digest_da({"day": DAY_S, "keys": 2, "keys_24h": 1}))

    def test_side_jobs_never_hide_an_idle_pipeline(self):
        from lab import watch
        self.db.event("system.running", "system:supervisor", None, {"pid": 1})
        t = self.db.one("SELECT MAX(ts) FROM events WHERE kind='system.running'")[0]
        self.db.event("job.done", "report-1", None, {"job_id": f"scan_digest|{DAY_S}", "kind": "scan_digest"})
        ok, why = watch._progress(self.path, t + 3 * 3600, {"status": "running"})
        self.assertFalse(ok)
        self.assertIn("no research work", why)
        r = command.research_progress(self.db)
        self.assertIsNone(r["last_job_done_ts"])
        self.assertIsNotNone(r["last_side_job_done_ts"])

    def test_a_dossier_that_only_says_observe_is_not_tagged_investigate(self):
        self.db.event("research.dossier", "system:report-1", None, {"key": self.KEY, "advice": "observe"})
        self.db.event("research.dossier", "system:report-1", None, {"key": self.KEY, "advice": "family_draft"})
        tags = [i["tag"] for i in command.feed(self.db)["items"][:2]]
        self.assertEqual(tags, ["UNDERSØG", "SØGNING"])


if __name__ == "__main__":
    unittest.main()
