"""Data coverage, source health and the hypothesis register (display only; research/AUDIT_2026-10-20.md)."""
import json
import os
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lab import coverage, web  # noqa: E402
from lab.db import DB  # noqa: E402

NOW = 1_792_500_000
PREMIUM = "https://fapi.binance.com/fapi/v1/premiumIndex"


def touch(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "wb").close()


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = DB(os.path.join(self.tmp.name, "lab.db"))
        self.root = os.path.join(self.tmp.name, "market")
        coverage._SCANNED.clear()

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def obs(self, ts, source, metric="perp_premium"):
        self.db._append("observations", ts=ts, detector="pricing_constraint/2", source=source, instrument="BTCUSDT",
                        metric=metric, value=0.0, threshold=None, flagged=0, payload="{}")


class Sources(Base):
    def test_cache_period_files_and_coins(self):
        for sym in ("BTCUSDT", "ETHUSDT"):
            for m in ("2020-01", "2021-06", "2023-12"):
                touch(os.path.join(self.root, "klines", f"{sym}-1h-{m}.zip"))
        touch(os.path.join(self.root, "funding", "BTCUSDT-fundingRate-2020-03.zip"))
        touch(os.path.join(self.root, "metrics", "BTCUSDT", "BTCUSDT-metrics-2022-01-01.zip"))   # nested, daily
        touch(os.path.join(self.root, "metrics", "x.lock"))
        s = {r["source"]: r for r in coverage.sources(self.db, NOW, self.root)["sources"]}
        um = s["Binance USD-M (data.binance.vision)"]
        self.assertEqual((um["files"], um["coins"], um["period"], um["health"]), (7, 2, "2020-01 .. 2023-12", "cached"))
        met = s["Binance metrics (data.binance.vision)"]
        self.assertEqual((met["files"], met["period"]), (1, "2022-01 .. 2022-01"))
        self.assertEqual(s["Binance spot (data.binance.vision)"]["health"], "missing")

    def test_registered_read_window_for_json_caches(self):
        touch(os.path.join(self.root, "fred", "DFII10-train3.json"))
        self.db._append("datasets", exp_id="E_x", split="train", source="https://fred.stlouisfed.org", path="p",
                        window_start=1640995200, window_end=1704067199, ts=NOW, sha256="0", size=1, purpose="t",
                        code_hash="c")
        fred = next(r for r in coverage.sources(self.db, NOW, self.root)["sources"] if r["source"] == "FRED")
        self.assertEqual(fred["period"], "2022-01-01 .. 2023-12-31")
        self.assertEqual(fred["registered_reads"], 1)

    def test_live_health(self):
        self.obs(NOW - 60, PREMIUM)
        self.obs(NOW - 30, PREMIUM, "error")
        self.obs(NOW - 2 * 86400, PREMIUM)                       # outside 24 h
        self.obs(NOW - 3600, "https://api.hyperliquid.xyz/info")   # older than 900 s
        self.obs(NOW - 3600, "https://gamma-api.polymarket.com/events/keyset")   # within its 2 h
        s = {r["source"]: r for r in coverage.sources(self.db, NOW, self.root)["sources"]}
        b = s["Binance fapi premiumIndex (live)"]
        self.assertEqual((b["rows_24h"], b["errors_24h"], b["health"]), (2, 1, "errors"))
        self.assertEqual(s["Hyperliquid info (live)"]["health"], "stale")
        self.assertEqual(s["Polymarket Gamma/CLOB (live)"]["health"], "ok")

    def test_an_error_hours_ago_is_counted_but_not_a_problem_now(self):
        self.obs(NOW - 60, PREMIUM)
        self.obs(NOW - 5 * 3600, PREMIUM, "error")               # last night's outage, recovered since
        b = next(r for r in coverage.sources(self.db, NOW, self.root)["sources"]
                 if r["source"] == "Binance fapi premiumIndex (live)")
        self.assertEqual((b["errors_24h"], b["health"], b["last_error_ts"]), (1, "ok", NOW - 5 * 3600))

    def test_a_source_whose_every_attempt_fails_is_failing_not_ok(self):
        """research/LINUX_DRIFT.md 2026-10-23: GDELT showed 'ok' with no item for 31 h because its error rows counted
        as its last sign of life."""
        gdelt = "https://api.gdeltproject.org/api/v2/doc/doc"
        self.obs(NOW - 31 * 3600, gdelt)                          # the last item
        self.obs(NOW - 15 * 3600, gdelt, "news_error")            # HTTP 429, then a 24 h backoff
        g = next(r for r in coverage.sources(self.db, NOW, self.root)["sources"] if r["source"].startswith("GDELT"))
        self.assertEqual((g["health"], g["last_ts"], g["age_s"]), ("failing", NOW - 31 * 3600, 31 * 3600))
        self.obs(NOW - 600, gdelt)                                # data again
        g = next(r for r in coverage.sources(self.db, NOW, self.root)["sources"] if r["source"].startswith("GDELT"))
        self.assertEqual(g["health"], "ok")

    def test_an_external_row_is_running_only_with_a_fresh_file(self):
        """research/LINUX_DRIFT.md 2026-10-23: X02/X03 were shown RUNNING with no data file on the host."""
        from unittest import mock
        from lab import legacy
        legacy.import_legacy(self.db)
        fresh = {"X01_pm_lp_v1": {"label": "pm_lp", "last_write_age_s": 30.0},
                 "X02_copybot_paper": {"label": "copy-bot paper process", "last_write_age_s": None},
                 "X03_funding_live_v0": {"label": "funding live", "last_write_age_s": 3 * 86400.0}}
        with mock.patch("lab.ops.external_freshness", lambda now=None: fresh):
            ex = {e["exp_id"]: e for m in coverage.hypotheses(self.db)["mechanisms"] for e in m["experiments"]}
        self.assertEqual(ex["X01_pm_lp_v1"]["verdict"], "RUNNING")
        self.assertEqual(ex["X02_copybot_paper"]["verdict"], "UNVERIFIED")
        self.assertIn("no data file of copy-bot paper process on this host", ex["X02_copybot_paper"]["verdict_text"])
        self.assertEqual(ex["X03_funding_live_v0"]["verdict"], "UNVERIFIED")
        self.assertIn("last write 72 h ago", ex["X03_funding_live_v0"]["verdict_text"])

    def test_never_seen_and_no_paid_source(self):
        out = coverage.sources(self.db, NOW, self.root)
        live = [r for r in out["sources"] if r["kind"] == "live"]
        self.assertTrue(all(r["health"] == "never seen" for r in live))
        self.assertEqual((out["paid_sources_active"], out["keys_used"]), (0, 0))
        self.assertTrue(all(r["key_needed"] == "no" for r in out["sources"]))
        self.assertIn("news history before amendment 16", [g["data"] for g in out["gaps"]])
        self.assertEqual(out["ingest"]["spent_bytes"], 0)
        pending = [r for r in out["sources"] if "amendment 14" in r["source"]]
        self.assertEqual({r["health"] for r in pending}, {"pending"})

    def test_fetch_pauses_only_data_fetch_in_24h(self):
        self.db.event("risk.pause", "system:risk", None, {"rule": "data_fetch", "detail": "reset"})
        self.db.event("risk.pause", "system:risk", None, {"rule": "spread_anomaly", "detail": "x"})
        out = coverage.sources(self.db, None, self.root)
        self.assertEqual([p["detail"] for p in out["fetch_pauses_24h"]], ["reset"])

    def test_scan_is_cached(self):
        touch(os.path.join(self.root, "klines", "BTCUSDT-1h-2020-01.zip"))
        coverage.sources(self.db, NOW, self.root)
        touch(os.path.join(self.root, "klines", "BTCUSDT-1h-2020-02.zip"))
        um = lambda t: next(r for r in coverage.sources(self.db, t, self.root)["sources"] if r["kind"] == "history")
        self.assertEqual(um(NOW + 10)["files"], 1)
        self.assertEqual(um(NOW + coverage.SCAN_TTL_S + 1)["files"], 2)


class Hypotheses(Base):
    def exp(self, eid, tag, hyp, version=1):
        self.db._append("experiments", exp_id=eid, version=version, created_ts=NOW, mechanism_tag=tag, fingerprint=eid,
                        spec_json=json.dumps({"hypothesis": hyp, "title": eid}), spec_path="", spec_commit="",
                        code_hash="c", note="")

    def result(self, eid, verdict):
        self.db._append("results", exp_id=eid, version=1, ts=NOW, label="x", verdict=verdict, metrics="{}",
                        evidence="{}", supersedes=None)

    def test_dedup_by_mechanism_and_status(self):
        self.exp("E_a", "funding_carry", "carry pays")
        self.exp("E_a", "funding_carry", "carry pays", version=2)       # same experiment, later version
        self.exp("E_b", "funding_carry", "carry pays, v2")
        self.exp("E_c", "momentum", "trend persists")
        self.exp("E_d", "untested", None)
        self.result("E_a", "REJECTED at train gate: x")
        self.result("E_b", "OBSERVE (forward test): y")
        self.result("E_c", "FAIL: z")
        for v in ("v1", "v2", "v2"):
            self.db._append("trials", exp_id="E_a", ts=NOW, variant=v, split="train", sharpe_daily=0.1, n_days=10,
                            net_total=0.0, params="{}")
        self.db._append("alpha_ledger", exp_id="E_b", ts=NOW, alpha=0.005, note="screen")
        self.db.event("research.explore", "system:backtest-1", None, {"evaluated": 40})
        self.db.event("research.explore", "system:backtest-1", None, {"evaluated": 10})
        h = coverage.hypotheses(self.db)
        m = {x["mechanism"]: x for x in h["mechanisms"]}
        self.assertEqual(len(m["funding_carry"]["experiments"]), 2)
        self.assertEqual(m["funding_carry"]["status"], "OBSERVE")
        self.assertEqual(m["funding_carry"]["variants_tested"], 2)
        self.assertAlmostEqual(m["funding_carry"]["alpha_spent"], 0.005)
        self.assertEqual(m["momentum"]["status"], "REJECTED")
        self.assertEqual(m["untested"]["status"], "NO RESULT")
        self.assertEqual(h["mechanisms"][0]["mechanism"], "funding_carry")       # strongest status first
        self.assertEqual((h["total_mechanisms"], h["total_experiments"], h["lane_variants_evaluated"]), (3, 4, 50))


class FinalStateOverrides(Hypotheses):
    def test_a_retired_experiment_is_rejected_whatever_its_screening_verdict(self):
        self.exp("E_v1", "volatility_managed_exposure", "scale exposure")
        self.exp("E_v2", "volatility_managed_exposure", "scale exposure, v2")
        self.result("E_v1", "PASS (screen): all validation gates passed")
        self.result("E_v2", "REJECTED at train gate: x")
        self.db.append("transitions", exp_id="E_v1", ts=NOW, from_state="SCREEN_PASSED", to_state="RETIRED",
                       actor="human:anton", reason="retired", evidence="{}")
        m = {x["mechanism"]: x for x in coverage.hypotheses(self.db)["mechanisms"]}["volatility_managed_exposure"]
        self.assertEqual(m["status"], "REJECTED")
        self.assertEqual([e["state"] for e in m["experiments"]], ["RETIRED", None])

    def test_a_live_screen_pass_stays_pass(self):
        self.exp("E_x", "momentum", "trend")
        self.result("E_x", "PASS (screen): ok")
        self.db.append("transitions", exp_id="E_x", ts=NOW, from_state="SCREENING", to_state="SCREEN_PASSED",
                       actor="system:x", reason="r", evidence="{}")
        self.assertEqual(coverage.hypotheses(self.db)["mechanisms"][0]["status"], "PASS")


class LaneMultipleTesting(Base):
    def review(self, p, ok, method="15"):
        self.db.event("research.lane_review", "system:adversarial-1", None,
                      {"key": f"k{p}{ok}", "ok": ok, "placebo_p": p, "method": method})

    def test_chance_and_bh(self):
        from lab import lane
        n = lane.REVIEW_PLACEBO_N
        for _ in range(18):
            self.review(0.5, False)
        self.review(2 / n, True)
        self.review(0.0, True)
        self.review(0.0, True, method=None)                     # an old-method review does not count
        r = coverage.lane_multiple_testing(self.db)
        self.assertEqual((r["tests"], r["passed_rule"], r["expected_by_chance"]), (20, 2, 2.0))
        self.assertEqual(sum(f["tests"] for f in r["by_function"]), 20)
        self.assertIn("not independent edges", r["note"])
        # conservative p: (0+1)/(n+1) and (2+1)/(n+1); BH needs p_(1) <= 0.1/20 = 0.005 -> none at n = 60
        self.assertEqual(r["bh_significant"], 0)

    def test_bh_passes_a_strong_result(self):
        with mock.patch("lab.lane.REVIEW_PLACEBO_N", 1000):
            self.review(0.0, True)
            self.review(0.9, False)
            self.assertEqual(coverage.lane_multiple_testing(self.db)["bh_significant"], 1)   # 1/1001 <= 0.05


class Progress(Base):
    """The user's directive point 7: results on the dashboard, display only."""
    def test_measurements_jobs_and_live_hours(self):
        now = time.time()
        self.db.event("research.measurement", "human:test", None, {"hypothesis": "H9", "name": "x", "verdict": "REJECTED",
                                                                   "reason": "train gate failed"})
        for h in range(3):
            self.db.append("observations", ts=int(now - h * 3600), detector="d/1", source="https://fapi.binance.com/fapi/v1/premiumIndex",
                           instrument="A", metric="perp_premium", value=0.1, threshold=None, flagged=0, payload={})
        p = coverage.sources(self.db, now=now)["progress"]
        self.assertEqual([(m["hypothesis"], m["verdict"]) for m in p["measurements"]], [("H9", "REJECTED")])
        live = {x["source"]: x["hours_with_data_24h"] for x in p["live_sources"]}
        self.assertEqual(live["Binance fapi premiumIndex (live)"], 3)
        self.assertEqual(live["GDELT DOC 2.0 (amendment 16)"], 0)
        self.assertEqual((p["jobs_done_24h"], p["jobs_failed_24h"]), (0, 0))

    def news(self, ts, title, coins, category="listing", backfill=False, fetched=None):
        p = {"title": title, "coins": coins, "category": category, "backfill": backfill,
             "fetched_ts": ts if fetched is None else fetched, "published_ts": ts - 60}
        self.db.append("observations", ts=int(ts), detector="news/1", source="binance", instrument=title,
                       metric="news_item", value=ts - 60, threshold=None, flagged=0, payload=p)

    def test_forward_tests_count_new_listing_announcements_only(self):
        t0 = coverage.FORWARD_FROM
        self.news(t0 - 3600, "Binance Futures Will Launch USDⓈ-M OLD Perpetual Contract", ["OLD"])     # before
        self.news(t0 + 60, "Binance Futures Will Launch USDⓈ-M AAA Perpetual Contract", ["AAA"])
        self.news(t0 + 120, "Binance Futures Will Launch BBB & CCC USDT-Margined Perpetual Contracts", ["BBB", "CCC"])
        self.news(t0 + 180, "Binance Futures Will Launch USDⓈ-M DDD Perpetual Contract", ["DDD"], backfill=True)
        self.news(t0 + 240, "Binance Futures Will Launch DDD Coin-Margined Perpetual Contract", ["DDD"])
        self.news(t0 + 300, "Binance Will List EEE (EEE)", ["EEE"])                                     # spot listing
        self.news(t0 + 360, "Binance Futures Will Delist FFFUSDT Perpetual Contract", ["FFF"], category="delisting")
        f = {x["hypothesis"]: x for x in coverage.forward(self.db, t0 + 400)}
        self.assertEqual(sorted(f), ["H5F", "H5X"])
        self.assertEqual((f["H5F"]["collected"], f["H5F"]["coins"], f["H5F"]["earliest_run_ts"]),
                         (3, ["AAA", "BBB", "CCC"], None))
        for i in range(20):
            self.news(t0 + 1000 + i, f"Binance Futures Will Launch USDⓈ-M X{i:02d} Perpetual Contract", [f"X{i:02d}"])
        f = {x["hypothesis"]: x for x in coverage.forward(self.db, t0 + 2000)}
        self.assertEqual(f["H5X"]["collected"], 20)
        self.assertEqual(f["H5X"]["earliest_run_ts"], t0 + 1016 - 60 + 7 * coverage.DAY)              # 20th: X16
        self.assertEqual(f["H5F"]["earliest_run_ts"], t0 + 1016 - 60 + 60 * coverage.DAY)


class Api(unittest.TestCase):
    def test_endpoints(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "lab.db")
            DB(path).close()
            srv = web.serve(path, 18793)
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            try:
                base = f"http://127.0.0.1:{srv.server_address[1]}"
                for p, key in (("/api/coverage", "sources"), ("/api/hypotheses", "mechanisms")):
                    with urllib.request.urlopen(base + p, timeout=10) as r:
                        self.assertEqual(r.status, 200)
                        self.assertIn(key, json.loads(r.read()))
            finally:
                srv.closing = True
                srv.shutdown()
                srv.server_close()


if __name__ == "__main__":
    unittest.main()
