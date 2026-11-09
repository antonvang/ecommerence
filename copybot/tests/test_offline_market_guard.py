"""Director orders 59-E/59-F P2/P3: the offline market fixture fails closed. With it active, the download layer never
goes to the network, never falls back to another cache and never opens a protected file; a missing fixture raises
OfflineFixtureMissing ("BLOCKED: no offline fixture"). Temporary files only: no real 2024 file, no network, no DNS."""
import builtins
import os
import shutil
import socket
import sys
import tempfile
import unittest
import urllib.request
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lab import pipeline  # noqa: E402
from lab.db import DB, HERE  # noqa: E402
from lab.engine import data  # noqa: E402
from tests import offline_market  # noqa: E402


class OfflineGuard(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="laboffline")
        self.real_cache = data.CACHE
        self.dns = []
        self.protected = []
        self.opened = []
        real_open = builtins.open

        def spy(file, *a, **k):                                         # every open() the code under test makes
            self.opened.append(os.fspath(file) if not isinstance(file, int) else file)
            return real_open(file, *a, **k)
        self.spy = mock.patch.object(builtins, "open", spy)
        self.spy.start()
        self.p = offline_market.patches(self.tmp) + offline_market.file_guard(self.protected) + [
            mock.patch("socket.getaddrinfo", lambda *a, **k: self.dns.append(a) or (_ for _ in ()).throw(
                AssertionError("DNS reached"))),
            mock.patch("socket.create_connection", lambda *a, **k: self.dns.append(a) or (_ for _ in ()).throw(
                AssertionError("network reached")))]
        for p in self.p:
            p.start()

    def tearDown(self):
        for p in reversed(self.p):
            p.stop()
        self.spy.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ---------- a missing fixture fails closed; no external endpoint ----------
    def test_a_missing_holdout_file_fails_closed_without_a_download(self):
        with self.assertRaises(offline_market.OfflineFixtureMissing) as cm:
            data.files_for("BNBUSDT", "holdout")
        self.assertTrue(str(cm.exception).startswith(offline_market.BLOCKED))
        self.assertIn("BNBUSDT-1h-2024-01.zip", str(cm.exception))
        self.assertEqual(os.listdir(data.CACHE), [])                     # nothing written
        self.assertEqual(self.dns, [])

    def test_no_fallback_to_external_endpoints(self):
        for url in ("https://data.binance.vision/x.zip", urllib.request.Request("https://fapi.binance.com/x")):
            with self.assertRaises(offline_market.OfflineFixtureMissing):
                urllib.request.urlopen(url)
        with self.assertRaises(offline_market.OfflineFixtureMissing):
            data._fetch("https://data.binance.vision/data/futures/um/monthly/klines/X/1h/X-1h-2024-01.zip",
                        os.path.join(self.tmp, "elsewhere", "X-1h-2024-01.zip"))
        self.assertEqual(self.dns, [])

    # ---------- no fallback to another cache ----------
    def test_a_decoy_cache_is_never_read(self):
        decoy = os.path.join(self.tmp, "decoy-market")
        zp = os.path.join(decoy, "klines", "BNBUSDT-1h-2024-01.zip")
        os.makedirs(os.path.dirname(zp))
        with open(zp, "wb") as fh:
            fh.write(b"decoy: must never be read")
        self.opened.clear()
        with mock.patch.object(data, "CACHE", decoy):                    # someone points the cache elsewhere
            with self.assertRaises(offline_market.OfflineFixtureMissing):
                data.files_for("BNBUSDT", "holdout")
        self.assertNotIn(zp, self.opened)
        self.assertEqual(self.dns, [])

    def test_the_real_cache_is_never_the_one_in_use(self):
        self.assertNotEqual(os.path.abspath(data.CACHE), os.path.abspath(self.real_cache))
        self.assertTrue(offline_market.in_temp(data.CACHE))

    def test_a_file_the_test_put_in_its_own_temporary_cache_is_used(self):
        p = os.path.join(data.CACHE, "klines", "SYN-1h-2023-01.zip")
        os.makedirs(os.path.dirname(p))
        with open(p, "wb") as fh:
            fh.write(b"synthetic")
        self.assertEqual(data._fetch("https://data.binance.vision/x", p), p)

    # ---------- no access to protected file paths ----------
    def test_protected_paths_cannot_be_opened(self):
        real = [os.path.join(HERE, "data", "lab", "market", "klines", "BNBUSDT-1h-2024-01.zip"),
                os.path.join(HERE, "data", "lab", "market", "funding", "anything.zip"),
                os.path.join(HERE, "BNBUSDT-1h-2024-01.zip"),
                os.path.join(HERE, "data", "lab", "lab.db"),
                os.path.join(HERE, "data", "research", "anything.json")]
        for p in real:
            existed = os.path.exists(p)                                 # a real checkout may hold lab.db or research data
            self.assertTrue(offline_market.protected(p), p)
            with self.assertRaises(offline_market.ProtectedFileAccess):
                open(p, "rb")
            with self.assertRaises(offline_market.ProtectedFileAccess):
                os.open(p, os.O_RDONLY)
            self.assertEqual(os.path.exists(p), existed, p)             # the guard raised before any file was made
        self.assertEqual(len(self.protected), 2 * len(real))
        self.assertFalse(offline_market.protected(os.path.join(self.tmp, "x", "data", "lab", "market", "a.zip")))
        self.assertFalse(offline_market.protected(os.path.join(HERE, "lab", "pipeline.py")))

    # ---------- synthetic holdout files work; the holdout gate is unchanged ----------
    def test_synthetic_files_are_temporary_stand_ins(self):
        f = offline_market.synthetic_files_for(self.tmp)("BTCUSDT", "holdout")
        for p in f["klines"] + f["funding"]:
            self.assertTrue(p.startswith(self.tmp))
            with open(p) as fh:
                self.assertIn("no market data", fh.read())

    def test_the_holdout_declaration_works_on_synthetic_files(self):
        db = DB(os.path.join(self.tmp, "lab.db"))
        try:
            eid = "E_day_of_week_p2"
            spec = {**pipeline.template_spec("day_of_week")}
            db.append("experiments", exp_id=eid, version=1, created_ts=0, mechanism_tag="m", fingerprint=eid,
                      spec_json=spec)
            db.append("transitions", exp_id=eid, ts=0, from_state=None, to_state="VALIDATION", actor="fixture",
                      reason="fixture: holdout opened")
            with mock.patch.object(data, "files_for", offline_market.synthetic_files_for(self.tmp)):
                shas = pipeline._declare_holdout(db, eid, pipeline._spec(db, eid), "t")
            self.assertTrue(shas)
            self.assertTrue(all(offline_market.in_temp(p) and "synthetic-" in p for p in shas))
            self.assertEqual(db.one("SELECT COUNT(*) FROM events WHERE kind='holdout.opened'")[0], 1)
            self.assertEqual(self.protected, [])
            self.assertEqual(self.dns, [])
        finally:
            db.close()


class QuarantineGuard(unittest.TestCase):
    """Order 73: synthetic stand-ins for the real open, so a broken guard could still not touch the protected file."""

    def setUp(self):
        self.assertTrue(offline_market.QUARANTINED)
        self.path = os.path.join("/some/checkout", offline_market.QUARANTINED[0])

    def test_detected_from_the_string_alone(self):
        with mock.patch("os.stat", side_effect=AssertionError("stat")), \
                mock.patch("os.lstat", side_effect=AssertionError("lstat")):
            self.assertTrue(offline_market.is_quarantined(self.path))
            self.assertTrue(offline_market.protected(self.path))
            self.assertTrue(offline_market.is_quarantined(os.fsencode(self.path)))
            self.assertFalse(offline_market.is_quarantined(3))

    def test_other_paths_pass(self):
        self.assertFalse(offline_market.is_quarantined("/some/checkout/research/data/QUARANTINE.json"))

    def test_wrappers_refuse_before_the_real_call(self):
        real_open, real_os_open = mock.Mock(), mock.Mock()
        guarded_open, guarded_os_open = offline_market.quarantine_wrappers(real_open, real_os_open)
        with self.assertRaises(offline_market.ProtectedFileAccess):
            guarded_open(self.path, "rb")
        with self.assertRaises(offline_market.ProtectedFileAccess):
            guarded_os_open(self.path, os.O_RDONLY)
        real_open.assert_not_called()
        real_os_open.assert_not_called()
        guarded_open("/elsewhere/file", "rb")
        real_open.assert_called_once()

    def test_file_guard_refuses_too(self):
        seen = []
        with mock.patch.object(builtins, "open", mock.Mock()) as real_open:
            patchers = offline_market.file_guard(seen)
            for x in patchers:
                x.start()
            try:
                with self.assertRaises(offline_market.ProtectedFileAccess):
                    builtins.open(self.path, "rb")
            finally:
                for x in reversed(patchers):
                    x.stop()
            real_open.assert_not_called()
        self.assertEqual(seen, [self.path])

    def test_process_guard_is_installed_by_the_tests_package(self):
        import tests
        self.assertTrue(tests.offline_market._process_guard)


if __name__ == "__main__":
    import direct_guard  # noqa: E402,F401  (order 75: quarantine guard for direct runs)
    unittest.main()
