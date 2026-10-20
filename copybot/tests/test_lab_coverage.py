"""Data coverage, source health and the hypothesis register (display only; research/AUDIT_2026-10-20.md)."""
import json
import os
import sys
import tempfile
import threading
import unittest
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

    def test_never_seen_and_no_paid_source(self):
        out = coverage.sources(self.db, NOW, self.root)
        live = [r for r in out["sources"] if r["kind"] == "live"]
        self.assertTrue(all(r["health"] == "never seen" for r in live))
        self.assertEqual((out["paid_sources_active"], out["keys_used"]), (0, 0))
        self.assertTrue(all(r["key_needed"] == "no" for r in out["sources"]))
        self.assertIn("news articles and headlines", [g["data"] for g in out["gaps"]])
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
