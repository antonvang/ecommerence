"""Read-only dashboard: pure data functions on a synthetic journal, and routing."""
import hashlib
import json
import tempfile
import unittest
from decimal import Decimal
from http import HTTPStatus
from pathlib import Path

from jupiter_bot.tests.guard import setUpModule, tearDownModule  # noqa: F401
from jupiter_bot import ops
from jupiter_bot.core import SOL, USDC, Rejected
from jupiter_bot.dashboard import data, server
from jupiter_bot.marketdata.journal import Journal

NOW = 1_800_000_000.0          # aligned to 60 s
SECRET = "5" * 88              # what a base58 private key would look like


def add_fetch(db, source, instrument, at, outcome="OK", error=None, kind="x"):
    return db.execute(
        """INSERT INTO fetches(source, kind, instrument, url, requested_at, received_at, http_status,
                               headers_json, body, body_sha256, outcome, error, summary_json)
           VALUES (?, ?, ?, 'https://example.invalid/', ?, ?, 200, '{}', NULL, NULL, ?, ?, '{}')""",
        (source, kind, instrument, at, at, outcome, error)).lastrowid


def add_bar(db, start, close, fetch_id):
    db.execute("INSERT INTO candles VALUES ('binance_spot_klines', 'SOL/USDC', 60, ?, ?, ?, ?, ?, ?, '1', ?, ?)",
               (start, start + 60, close, close, close, close, start + 67, fetch_id))


def add_quote(db, side, at, out_amount, fetch_id, in_amount=None):
    mints = (USDC.mint, SOL.mint) if side == "buy" else (SOL.mint, USDC.mint)
    in_amount = in_amount or (data.BUY_IN_ATOMS if side == "buy" else data.SELL_IN_ATOMS)
    db.execute("INSERT INTO quotes VALUES (?, ?, ?, ?, ?, 'metis', 2, ?, ?, ?)",
               (hashlib.sha256(("%s%s%s" % (side, at, in_amount)).encode()).hexdigest(), mints[0], mints[1],
                in_amount, out_amount, at - 0.1, at, fetch_id))


def build_journal(path, minutes=120, skip=(), errors_at=()):
    """Two hours of 1m bars at close 100 (with a hole), quotes each minute, hourly news sources."""
    journal = Journal(path)
    db = journal.db
    db.execute("BEGIN")
    for source in ("solana_status", "jupiter_status", "agave_releases"):
        add_fetch(db, source, None, NOW - 3600 - 30)
    for i in range(minutes, 0, -1):
        tick = NOW - i * 60 + 7
        start = NOW - (i + 1) * 60
        fid = add_fetch(db, "binance_spot_klines", "SOL/USDC", tick,
                        "TRANSPORT_ERROR" if i in errors_at else "OK", "Request failed" if i in errors_at else None)
        if i not in skip and i not in errors_at:
            add_bar(db, start, "100", fid)
        buy = add_fetch(db, "jupiter_quote", "USDC/SOL", tick + 1)
        add_quote(db, "buy", tick + 1, 249_500_000, buy)          # 25 USDC -> 0.2495 SOL = 100.2004 USDC/SOL
        sell = add_fetch(db, "jupiter_quote", "SOL/USDC", tick + 2)
        add_quote(db, "sell", tick + 2, 34_930_000, sell)          # 0.35 SOL -> 34.93 USDC = 99.8 USDC/SOL
    other = add_fetch(db, "jupiter_quote", "USDC/SOL", NOW - 5)
    add_quote(db, "buy", NOW - 5, 9_000_000_000, other, in_amount=1_000_000_000)   # 1000 USDC: other size
    db.execute("COMMIT")
    journal.close()


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class Base(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        root = Path(self.directory.name)
        self.repo = root / "repo"
        (self.repo / "jupiter_bot" / "research").mkdir(parents=True)
        self.paths = data.Paths(journal=root / "data" / "observations.db", data_dir=root / "data",
                                mandate=root / "config" / "mandate.json", repo=self.repo)
        self.paths.data_dir.mkdir()

    def tearDown(self):
        self.directory.cleanup()


class Prices(unittest.TestCase):
    def test_buy_price_from_atoms(self):
        price = data.price_usdc_per_sol(USDC.mint, SOL.mint, 25_000_000, 363_990_525)
        self.assertEqual(price, Decimal("25") / Decimal("0.363990525"))
        self.assertAlmostEqual(float(price), 68.6831, places=4)

    def test_sell_price_from_atoms(self):
        price = data.price_usdc_per_sol(SOL.mint, USDC.mint, 350_000_000, 24_029_219)
        self.assertEqual(price, Decimal("24.029219") / Decimal("0.35"))
        self.assertAlmostEqual(float(price), 68.6549, places=4)

    def test_rejects_other_pairs_and_bad_amounts(self):
        with self.assertRaises(Rejected):
            data.price_usdc_per_sol(SOL.mint, SOL.mint, 1, 1)
        for bad in ((0, 1), (1, 0), (True, 1), (1.5, 1), ("1", 1)):
            with self.assertRaises(Rejected):
                data.price_usdc_per_sol(USDC.mint, SOL.mint, *bad)

    def test_gap_bps_positive_means_worse_than_binance(self):
        self.assertEqual(data.gap_bps("buy", Decimal("100.5"), Decimal("100")), 50)
        self.assertEqual(data.gap_bps("sell", Decimal("99.5"), Decimal("100")), 50)
        self.assertEqual(data.gap_bps("sell", Decimal("100.5"), Decimal("100")), -50)
        with self.assertRaises(Rejected):
            data.gap_bps("buy", 1, 0)
        with self.assertRaises(Rejected):
            data.gap_bps("hold", 1, 1)

    def test_bucket_size_keeps_points_bounded(self):
        self.assertEqual(data.bucket_seconds(6), 60)
        self.assertEqual(data.bucket_seconds(24), 120)
        self.assertEqual(data.bucket_seconds(168), 900)
        self.assertLessEqual(168 * 3600 / data.bucket_seconds(168), data.MAX_POINTS)


class EmptyStates(Base):
    def test_everything_absent_renders_and_creates_nothing(self):
        overview = data.overview(self.paths, NOW)
        self.assertEqual(overview["status"]["level"], "error")
        self.assertIn("Journal findes ikke", overview["status"]["problems"][0])
        self.assertEqual(overview["backups"], {"count": 0, "newest": None})
        market = data.market(self.paths, 24, NOW)
        self.assertEqual(market["series"]["binance"], [])
        self.assertIn("error", market)
        research = data.research(self.paths, NOW)
        self.assertEqual(research["state"], "missing")
        self.assertEqual(research["evaluations"], {"exists": False, "runs": [], "errors": []})
        self.assertIsNone(research["progress"]["development"])
        self.assertEqual(data.paper(self.paths, NOW)["exists"], False)
        execution = data.execution(self.paths, NOW)
        self.assertEqual((execution["built"], execution["mode"], execution["mandate"]), (False, "DISARMED", None))
        self.assertEqual({g["name"] for g in execution["gates"]},
                         {"p2_plan_locked", "p2_holdout_pass", "mandate_present", "mandate_not_expired",
                          "execution_built"})
        self.assertFalse(self.paths.journal.exists())
        self.assertEqual(sorted(p.name for p in self.paths.data_dir.iterdir()), [])
        json.dumps([overview, market, research, execution], allow_nan=False)

    def test_foreign_database_is_refused_not_touched(self):
        import sqlite3
        db = sqlite3.connect(str(self.paths.journal))
        db.execute("CREATE TABLE wallets(x)")
        db.commit()
        db.close()
        before = digest(self.paths.journal)
        self.assertEqual(data.overview(self.paths, NOW)["status"]["level"], "error")
        self.assertEqual(digest(self.paths.journal), before)


class WithJournal(Base):
    def setUp(self):
        super().setUp()
        build_journal(self.paths.journal, skip=(30, 31), errors_at=(10,))

    def test_first_rowid_since_finds_the_window(self):
        journal = Journal(self.paths.journal, readonly=True)
        try:
            cutoff = data.first_rowid_since(journal.db, "fetches", "requested_at", NOW - 600)
            first = journal.db.execute("SELECT min(requested_at) FROM fetches WHERE rowid>=?", (cutoff,)).fetchone()[0]
            before = journal.db.execute("SELECT requested_at FROM fetches WHERE rowid=?", (cutoff - 1,)).fetchone()[0]
            self.assertGreaterEqual(first, NOW - 600)
            self.assertLess(before, NOW - 600)
            self.assertIsNone(data.first_rowid_since(journal.db, "limiter", "last_requested_at", 0))
            last = journal.db.execute("SELECT max(rowid) FROM fetches").fetchone()[0]
            self.assertEqual(data.first_rowid_since(journal.db, "fetches", "requested_at", NOW + 1), last + 1)
        finally:
            journal.close()

    def test_overview_counts_gaps_and_errors_without_writing(self):
        before = digest(self.paths.journal)
        overview = data.overview(self.paths, NOW)
        self.assertEqual(digest(self.paths.journal), before)
        rows = {(r["source"], r["instrument"]): r for r in overview["sources"]}
        binance = rows[("binance_spot_klines", "SOL/USDC")]
        self.assertEqual((binance["ok_24h"], binance["errors_24h"], binance["errors_1h"]), (119, 1, 1))
        self.assertAlmostEqual(binance["error_rate_24h"], 1 / 120)
        self.assertEqual(binance["last_error"]["outcome"], "TRANSPORT_ERROR")
        self.assertEqual(rows[("jupiter_quote", "USDC/SOL")]["ok_24h"], 121)
        self.assertFalse(any(r["stale"] for r in overview["sources"]))
        # Bars 31, 30 (skipped) and 10 (fetch failed) are missing: two holes, three bars.
        self.assertEqual(overview["candles"]["gaps_24h"], 2)
        self.assertEqual(overview["candles"]["missing_bars_24h"], 3)
        self.assertEqual(overview["candles"]["missing_bars_total"], 3)
        self.assertEqual(overview["status"]["level"], "warning")
        self.assertEqual(overview["status"]["problems"], [])
        self.assertAlmostEqual(overview["days_collected"], 3630 / 86400, places=6)
        self.assertEqual(overview["last_cycle_at"], NOW - 5)

    def test_staleness_follows_ops_rules(self):
        later = NOW + ops.MAX_AGE["jupiter_quote"] + 60
        overview = data.overview(self.paths, later)
        self.assertEqual(overview["status"]["level"], "error")
        self.assertEqual(overview["status"]["problems"],
                         ops.stale_sources({"outcomes": [
                             {"source": "binance_spot_klines", "outcome": "OK", "last": NOW - 60 + 7},
                             {"source": "jupiter_quote", "outcome": "OK", "last": NOW - 5},
                             {"source": "solana_status", "outcome": "OK", "last": NOW - 3630},
                             {"source": "jupiter_status", "outcome": "OK", "last": NOW - 3630},
                             {"source": "agave_releases", "outcome": "OK", "last": NOW - 3630}]}, later))

    def test_backups_and_health_state_are_reported(self):
        (self.paths.backups).mkdir()
        (self.paths.backups / "observations-2027-01-14.db").write_bytes(b"x" * 10)
        (self.paths.backups / "observations-2027-01-15.db").write_bytes(b"x" * 20)
        (self.paths.backups / "notes.txt").write_text("ignored")
        self.paths.health_state.write_text(json.dumps({"stale": [], "last_alert": None}))
        overview = data.overview(self.paths, NOW)
        self.assertEqual(overview["backups"]["count"], 2)
        self.assertEqual(overview["backups"]["newest"]["date"], "2027-01-15")
        self.assertEqual(overview["backups"]["newest"]["bytes"], 20)
        self.assertEqual(overview["health_state"]["stale"], [])

    def test_market_prices_gaps_and_downsampling(self):
        before = digest(self.paths.journal)
        market = data.market(self.paths, 6, NOW)
        self.assertEqual(digest(self.paths.journal), before)
        self.assertEqual(market["bucket_s"], 60)
        self.assertEqual(market["counts"]["other_sizes"], 1)
        self.assertEqual(market["counts"]["quotes_buy"], 120)
        latest = market["latest"]
        self.assertAlmostEqual(latest["buy"]["price"], 100.200401, places=6)
        self.assertAlmostEqual(latest["sell"]["price"], 99.8, places=6)
        self.assertAlmostEqual(latest["buy"]["gap_bps"], 20.04, places=2)
        self.assertAlmostEqual(latest["sell"]["gap_bps"], 20.0, places=2)
        self.assertEqual(market["summary"]["round_trip_median_bps"], 40.04)
        self.assertEqual(market["summary"]["binance_last"], 100.0)
        self.assertEqual(len(market["series"]["binance"]), 117)
        # Quotes right after a missing bar have no bar to compare against.
        self.assertGreater(market["counts"]["unmatched"], 0)
        week = data.market(self.paths, 168, NOW)
        self.assertEqual(week["bucket_s"], 900)
        self.assertLessEqual(len(week["series"]["buy"]), 9)
        self.assertEqual(data.market(self.paths, "nonsense", NOW)["hours"], 24.0)
        self.assertEqual(data.market(self.paths, 10 ** 9, NOW)["hours"], 24.0 * 31)
        json.dumps(market, allow_nan=False)


class Research(Base):
    def write_lock(self):
        self.paths.research.mkdir(parents=True, exist_ok=True)
        self.paths.plan_lock.write_text(json.dumps({
            "plan_path": "jupiter_bot/research/P2_PLAN.md", "plan_sha256": "a" * 64,
            "code_sha256": {"jupiter_bot/research/strategies.py": "b" * 64}, "git_commit": "c" * 40,
            "locked_at": NOW - 7200, "approved_by": "Anton",
            "development": {"start": NOW - 7200, "end": NOW + 7200}, "holdout": {"start": NOW + 7200, "end": NOW + 14400}}))

    def write_run(self, name, label, created_at, plan="a" * 64, **extra):
        self.paths.evaluations.mkdir(parents=True, exist_ok=True)
        run = {"run_id": name, "created_at": created_at, "kind": "replay", "label": label, "plan_sha256": plan,
               "strategy": "momentum", "params": {"lookback": 60}, "delay_s": 60, "extra_cost_bps": 5,
               "metrics": {"return_pct": "1.5", "max_drawdown_pct": "-3.0", "trades": 12, "missing": 1},
               "benchmarks": {"hold_sol_return_pct": "2.0", "cash_return_pct": "0"},
               "controls": {"random_entries": {"runs": 200, "share_beating_strategy": "0.42"}},
               "verdict": None}
        run.update(extra)
        (self.paths.evaluations / (name + ".json")).write_text(json.dumps(run))

    def test_draft_plan_without_lock(self):
        (self.repo / "jupiter_bot" / "research" / "P2_PLAN.md").write_text("# plan")
        research = data.research(self.paths, NOW)
        self.assertEqual(research["state"], "draft")
        self.assertFalse(research["lock"]["exists"])

    def test_locked_plan_progress_and_evaluation_listing(self):
        build_journal(self.paths.journal)
        self.write_lock()
        self.write_run("r1", "development", NOW - 100)
        self.write_run("r2", "holdout", NOW - 50, verdict="FAIL")
        self.write_run("r3", "development", NOW - 10, plan="f" * 64)
        (self.paths.evaluations / "broken.json").write_text("{not json")
        research = data.research(self.paths, NOW)
        self.assertEqual(research["state"], "locked")
        self.assertEqual(research["lock"]["approved_by"], "Anton")
        dev, holdout = research["progress"]["development"], research["progress"]["holdout"]
        self.assertEqual(dev["state"], "i gang")
        self.assertAlmostEqual(dev["covered_share"], 0.5, places=2)   # 2 h of data in a 4 h window
        self.assertEqual((holdout["state"], holdout["covered_share"]), ("ikke startet", 0.0))
        runs = research["evaluations"]["runs"]
        self.assertEqual([r["run_id"] for r in runs], ["r3", "r2", "r1"])
        self.assertEqual(runs[1]["label"], "holdout")
        self.assertEqual(runs[1]["verdict"], "FAIL")
        self.assertAlmostEqual(runs[2]["excess_vs_hold_pct"], -0.5)
        self.assertAlmostEqual(runs[2]["random_share_beating"], 0.42)
        self.assertEqual([r["matches_lock"] for r in runs], [False, True, True])
        self.assertEqual(research["evaluations"]["errors"][0]["file"], "broken.json")
        json.dumps(research, allow_nan=False)

    def test_invalid_lock_is_shown_not_trusted(self):
        self.paths.research.mkdir(parents=True)
        self.paths.plan_lock.write_text('{"plan_sha256": "a", "plan_sha256": "b"}')
        research = data.research(self.paths, NOW)
        self.assertEqual(research["state"], "invalid")
        self.assertIn("Duplicate", research["lock"]["error"])


class PaperAndExecution(Base):
    def test_forward_paper_reads_view_files_read_only(self):
        self.paths.forward_paper.mkdir(parents=True)
        view = self.paths.forward_paper / "tsmom-0.json"
        view.write_text(json.dumps({
            "status": "OK", "strategy": "tsmom", "params": {"lookback_min": 240}, "grid_index": 0,
            "updated_at": NOW, "period": {"start": NOW - 7200, "end": NOW - 120}, "now_target": "FLAT",
            "metrics": {"return_pct": "1.5", "trades": 4, "round_trips": 2, "open_position_at_end": False},
            "benchmarks": {"hold_sol_return_pct": "-0.5"},
            "equity": [[NOW - 7200 + 60 * i, 25.01 + i * 0.001] for i in range(1000)]}))
        (self.paths.forward_paper / "broken.json").write_text("{")
        before = digest(view)
        paper = data.paper(self.paths, NOW)
        self.assertTrue(paper["exists"])
        [row] = paper["configs"]
        self.assertEqual((row["strategy"], row["now_target"], row["return_pct"]), ("tsmom", "FLAT", 1.5))
        self.assertLessEqual(len(row["series"]["strategy"]), data.FORWARD_POINTS)
        self.assertAlmostEqual(row["series"]["strategy"][0][1], 0.0)
        self.assertEqual([e["file"] for e in paper["errors"]], ["broken.json"])
        self.assertEqual(digest(view), before)

    def test_mandate_shows_only_public_whitelisted_fields(self):
        self.paths.mandate.parent.mkdir(parents=True)
        self.paths.mandate.write_text(json.dumps({
            "wallet_pubkey": "9xQeWvG816bUx9EPjHmaT23yvVM2ZWbrrpZb9PusVFin", "max_position_usdc": 100,
            "max_trade_usdc": 25, "daily_loss_limit_usdc": 10, "allowed_mints": [SOL.mint, USDC.mint],
            "expires_at": NOW + 86400, "secret_key": SECRET, "note": "x"}))
        execution = data.execution(self.paths, NOW)
        text = json.dumps(execution)
        self.assertNotIn(SECRET, text)
        self.assertNotIn("secret_key", text)
        mandate = execution["mandate"]
        self.assertEqual(mandate["hidden_fields"], 2)
        self.assertEqual([m["symbol"] for m in mandate["allowed_mints"]], ["SOL", "USDC"])
        gates = {g["name"]: g["ok"] for g in execution["gates"]}
        self.assertEqual((gates["mandate_present"], gates["mandate_not_expired"]), (True, True))

    def test_secret_in_pubkey_field_is_not_shown(self):
        self.paths.mandate.parent.mkdir(parents=True)
        self.paths.mandate.write_text(json.dumps({"wallet_pubkey": SECRET}))
        execution = data.execution(self.paths, NOW)
        self.assertNotIn(SECRET, json.dumps(execution))
        self.assertTrue(execution["mandate"]["warnings"])

    def test_built_execution_status_is_validated(self):
        (self.repo / "jupiter_bot" / "execution").mkdir()
        status = {"armed": True, "mode": "LIVE", "mandate": {"wallet_pubkey": SECRET},
                  "gates": [{"name": "p2_holdout_pass", "ok": True, "detail": "ok"}],
                  "orders": {"total": 3, "pending": 0, "confirmed": 2, "failed": 1, "unknown": 0},
                  "today_realized_pnl_usdc": -1.5}
        execution = data.execution(self.paths, NOW, runner=lambda paths: status)
        self.assertEqual((execution["mode"], execution["armed"]), ("LIVE", True))
        self.assertEqual(execution["orders"]["confirmed"], 2)
        self.assertNotIn(SECRET, json.dumps(execution))
        weird = data.execution(self.paths, NOW, runner=lambda paths: dict(status, mode="YOLO"))
        self.assertEqual(weird["mode"], "UKENDT")

        def broken(paths):
            raise Rejected("execution status exit 2")
        failed = data.execution(self.paths, NOW, runner=broken)
        self.assertEqual((failed["mode"], failed["status_error"]), ("DISARMED", "execution status exit 2"))


class Routing(Base):
    def test_only_get_is_allowed(self):
        for method in ("POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS", "FOO"):
            status, headers, body = server.route(method, "/api/overview", self.paths, NOW)
            self.assertEqual(status, HTTPStatus.METHOD_NOT_ALLOWED, method)
            self.assertEqual(headers["Allow"], "GET")
        self.assertFalse(self.paths.journal.exists())

    def test_handler_maps_every_other_method_to_405(self):
        handler = server.Handler.__new__(server.Handler)
        self.assertEqual(handler.do_PATCH, handler._not_allowed)
        self.assertEqual(handler.do_WHATEVER, handler._not_allowed)
        with self.assertRaises(AttributeError):
            handler.something_else

    def test_get_routes(self):
        build_journal(self.paths.journal)
        status, headers, body = server.route("GET", "/", self.paths, NOW)
        self.assertEqual(status, HTTPStatus.OK)
        self.assertTrue(headers["Content-Type"].startswith("text/html"))
        self.assertIn(b"<title>", body)
        self.assertNotIn(b"https://", body)            # no CDN, fonts or other external resources
        for path in ("/api/overview", "/api/market?hours=6", "/api/research", "/api/paper", "/api/execution"):
            status, headers, body = server.route("GET", path, self.paths, NOW)
            self.assertEqual(status, HTTPStatus.OK, path)
            self.assertIsInstance(json.loads(body), dict)
        self.assertEqual(json.loads(server.route("GET", "/api/market?hours=6", self.paths, NOW)[2])["hours"], 6.0)
        self.assertEqual(server.route("GET", "/../etc/passwd", self.paths, NOW)[0], HTTPStatus.NOT_FOUND)
        self.assertEqual(server.route("GET", "/static/index.html", self.paths, NOW)[0], HTTPStatus.NOT_FOUND)

    def test_foreign_host_header_is_refused(self):
        self.assertEqual(server.route("GET", "/api/overview", self.paths, NOW, host="evil.example:8787")[0],
                         HTTPStatus.FORBIDDEN)
        for host in ("127.0.0.1:8787", "localhost:8787", None):
            self.assertNotEqual(server.route("GET", "/", self.paths, NOW, host=host)[0], HTTPStatus.FORBIDDEN)

    def test_server_binds_to_loopback_only(self):
        self.assertEqual(server.HOST, "127.0.0.1")
        self.assertEqual(server.DEFAULT_PORT, 8787)
        httpd = server.make_server(self.paths, port=0)    # bind only; nothing connects
        try:
            self.assertEqual(httpd.server_address[0], "127.0.0.1")
        finally:
            httpd.server_close()


if __name__ == "__main__":
    unittest.main()
