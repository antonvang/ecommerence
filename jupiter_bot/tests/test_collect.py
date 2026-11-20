"""The scheduled collection cycle, offline. One cycle per timer tick; no loop."""
import io
import json
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from jupiter_bot.tests.guard import setUpModule, tearDownModule  # noqa: F401
from jupiter_bot.__main__ import main
from jupiter_bot.marketdata import collect
from jupiter_bot.marketdata.journal import Journal
from jupiter_bot.marketdata.transport import RawResponse, TransportError
from jupiter_bot.tests.test_marketdata import ATOM_BODY, RSS_BODY, STATUS_BODY, T0, body, http_date, kline

REPO = Path(__file__).resolve().parents[2]


class Source:
    """Fake upstreams keyed by host; counts calls."""

    def __init__(self, clock):
        self.clock, self.calls, self.override = clock, [], {}

    def __call__(self, url, endpoint):
        parts = urlsplit(url)
        self.calls.append(parts.netloc)
        if parts.netloc in self.override:
            response = self.override[parts.netloc]
            if isinstance(response, Exception):
                raise response
            return response
        if parts.netloc == "api.binance.com":
            index = int((self.clock[0] - T0) // 60)
            return RawResponse(200, {"date": http_date(self.clock[0])},
                               body([kline(i) for i in range(index - 9, index + 1)]))
        if parts.netloc == "api.jup.ag":
            query = {k: v[0] for k, v in parse_qs(parts.query).items()}
            return RawResponse(200, {}, json.dumps(dict(query, inAmount=query["amount"], outAmount="1000",
                                                        router="metis", feeBps=2, transaction=None)).encode())
        if parts.netloc == "status.solana.com":
            return RawResponse(200, {}, json.dumps(STATUS_BODY).encode())
        if parts.netloc == "status.jup.ag":
            return RawResponse(200, {}, RSS_BODY)
        return RawResponse(200, {}, ATOM_BODY)


class Cycle(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.journal = Journal(Path(self.directory.name) / "j.db")
        self.clock = [float(T0 + 3600 + 7)]
        self.sleeps = []
        self.source = Source(self.clock)

    def tearDown(self):
        self.journal.close()
        self.directory.cleanup()

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.clock[0] += seconds

    def cycle(self):
        return collect.collect(self.journal, fetch=self.source, clock=lambda: self.clock[0], sleep=self.sleep)

    def statuses(self, report):
        return {entry["job"]: entry["status"] for entry in report}

    def test_first_cycle_runs_everything_and_paces_jupiter(self):
        report = self.cycle()
        self.assertEqual(set(self.statuses(report).values()), {"OK"})
        self.assertEqual(len(self.source.calls), 6)
        self.assertEqual(len(self.sleeps), 1)  # second Jupiter quote waited for the 2.1 s interval
        self.assertEqual(collect.exit_code(report), 0)

    def test_only_due_jobs_run_on_later_ticks(self):
        self.cycle()
        self.clock[0] += 30
        self.assertEqual(set(self.statuses(self.cycle()).values()), {"NOT_DUE"})
        self.clock[0] += 30  # one minute after the first tick
        statuses = self.statuses(self.cycle())
        self.assertEqual(statuses["candles_1m"], "OK")
        self.assertEqual(statuses["quote_buy_25usdc"], "OK")
        self.assertEqual(statuses["solana_status"], "NOT_DUE")
        self.clock[0] = T0 + 3600 + 7 + 3600
        self.assertEqual(self.statuses(self.cycle())["agave_releases"], "OK")

    def test_cooldown_skips_without_request_or_journal_spam(self):
        self.source.override["api.binance.com"] = RawResponse(429, {"retry-after": "300"}, b"{}")
        self.assertEqual(self.statuses(self.cycle())["candles_1m"], "FAILED")
        del self.source.override["api.binance.com"]
        calls_before = len(self.source.calls)
        rows_before = self.journal.db.execute("SELECT count(*) FROM fetches").fetchone()[0]
        self.clock[0] += 60
        report = self.cycle()
        self.assertEqual(self.statuses(report)["candles_1m"], "COOLING_DOWN")
        self.assertNotIn("api.binance.com", self.source.calls[calls_before:])
        rows_after = self.journal.db.execute("SELECT count(*) FROM fetches WHERE source='binance_spot_klines'")
        self.assertEqual(rows_after.fetchone()[0], 1)
        self.assertGreater(self.journal.db.execute("SELECT count(*) FROM fetches").fetchone()[0], rows_before)
        self.clock[0] += 300
        self.assertEqual(self.statuses(self.cycle())["candles_1m"], "OK")

    def test_one_broken_source_does_not_stop_the_others_and_is_journaled(self):
        self.source.override["status.jup.ag"] = RuntimeError("unexpected bug in transport")
        self.source.override["github.com"] = TransportError("Request failed: URLError")
        report = self.cycle()
        statuses = self.statuses(report)
        self.assertEqual((statuses["jupiter_status"], statuses["agave_releases"]), ("FAILED", "FAILED"))
        self.assertEqual(statuses["candles_1m"], "OK")
        self.assertEqual(collect.exit_code(report), 1)
        errors = [row[0] for row in self.journal.db.execute(
            "SELECT error FROM fetches WHERE outcome='TRANSPORT_ERROR' ORDER BY id")]
        self.assertEqual(len(errors), 2)
        self.assertIn("RuntimeError", errors[0])

    def test_exit_code_when_everything_fails(self):
        for host in ("api.binance.com", "api.jup.ag", "status.solana.com", "status.jup.ag", "github.com"):
            self.source.override[host] = TransportError("offline")
        report = self.cycle()
        self.assertEqual(collect.exit_code(report), 2)
        self.assertEqual(collect.exit_code([dict(job="x", status="NOT_DUE")]), 0)

    def test_cli_collect_prints_one_line_and_returns_code(self):
        path = Path(self.directory.name) / "cli.db"
        source = Source([float(T0 + 3600 + 7)])
        out = io.StringIO()
        now = [float(T0 + 3600 + 7)]
        fake_time = SimpleNamespace(time=lambda: now[0], sleep=lambda seconds: now.__setitem__(0, now[0] + seconds))
        # Only collect's own `time` name is replaced; collect hands its clock to observe.
        with patch("jupiter_bot.marketdata.collect.https_get", source), \
                patch("jupiter_bot.marketdata.collect.time", fake_time), redirect_stdout(out):
            code = main(["collect", "--journal", str(path)])
        lines = out.getvalue().strip().splitlines()
        self.assertEqual(code, 0, lines)
        self.assertEqual(len(lines), 1)
        self.assertEqual(len(json.loads(lines[0])["jobs"]), len(collect.SCHEDULE))
        self.assertEqual(code, 0)


class Installer(unittest.TestCase):
    SCRIPT = REPO / "jupiter_bot" / "deploy" / "linux" / "install-collector.sh"

    def test_shell_syntax(self):
        for name in ("install-collector.sh", "uninstall-collector.sh"):
            result = subprocess.run(["bash", "-n", str(self.SCRIPT.parent / name)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_refuses_journal_inside_repository_before_anything_else(self):
        with tempfile.TemporaryDirectory() as directory:
            env = dict(JUPITER_DATA_DIR=str(REPO / "jupiter_bot" / "runtime" / "x"),
                       JUPITER_UNIT_DIR=directory, HOME=directory, PATH="/usr/bin:/bin")
            result = subprocess.run(["bash", str(self.SCRIPT), "--dry-run"], capture_output=True, text=True,
                                    env=env, timeout=60)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("outside the repository", result.stderr)
            self.assertEqual(list(Path(directory).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
