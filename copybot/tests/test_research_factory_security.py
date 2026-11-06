"""Director order 49 P1: factory security components, attack tests with throwaway keys and synthetic data."""
import hashlib
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from research.tools import factory_security as fx  # noqa: E402


def keypair(d, name):
    path = os.path.join(d, name)
    subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", name, "-f", path], check=True)
    with open(path + ".pub", encoding="utf-8") as f:
        return path, f.read().strip()


class Keys(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        d = tempfile.mkdtemp()
        cls.root, cls.root_pub = keypair(d, "owner_root_test")
        cls.second, cls.second_pub = keypair(d, "owner_second_test")
        cls.assistant, cls.assistant_pub = keypair(d, "assistant_test")
        cls.anchor = fx.fingerprint(cls.root_pub)

    def entry(self, action, pub, seq, signer):
        e = fx.keyreg_entry(action, pub, seq, 100 + seq)
        return e, fx.ssh_sign(e, signer, fx.NS_KEYREG)

    # 1. key binding
    def test_root_must_match_external_anchor(self):
        reg = [self.entry("add", self.root_pub, 0, self.root)]
        self.assertEqual(fx.KeyRegistry.valid_keys(reg, self.anchor), [self.root_pub])
        fake = [self.entry("add", self.assistant_pub, 0, self.assistant)]
        with self.assertRaises(fx.SecurityError):
            fx.KeyRegistry.valid_keys(fake, self.anchor)

    def test_added_key_needs_a_valid_signer(self):
        reg = [self.entry("add", self.root_pub, 0, self.root), self.entry("add", self.second_pub, 1, self.root)]
        self.assertEqual(len(fx.KeyRegistry.valid_keys(reg, self.anchor)), 2)
        sneaky = [self.entry("add", self.root_pub, 0, self.root),
                  self.entry("add", self.assistant_pub, 1, self.assistant)]      # self-added key
        with self.assertRaises(fx.SecurityError):
            fx.KeyRegistry.valid_keys(sneaky, self.anchor)

    def test_rotation_and_revocation(self):
        reg = [self.entry("add", self.root_pub, 0, self.root), self.entry("add", self.second_pub, 1, self.root),
               self.entry("revoke", self.root_pub, 2, self.second)]
        self.assertEqual(fx.KeyRegistry.valid_keys(reg, self.anchor), [self.second_pub])
        after = reg + [self.entry("add", self.assistant_pub, 3, self.root)]     # signed by the revoked key
        with self.assertRaises(fx.SecurityError):
            fx.KeyRegistry.valid_keys(after, self.anchor)

    def test_reordered_registry_is_refused(self):
        a, b = self.entry("add", self.root_pub, 0, self.root), self.entry("add", self.second_pub, 1, self.root)
        with self.assertRaises(fx.SecurityError):
            fx.KeyRegistry.valid_keys([b, a], self.anchor)

    # 2. checkpoint
    def log(self, n, tag="a"):
        return [{"seq": i, "hash": hashlib.sha256(f"{tag}{i}".encode()).hexdigest()} for i in range(n)]

    def test_checkpoint_detects_rollback_truncation_fork_forgery(self):
        log = self.log(5)
        cp = fx.checkpoint_statement("s1", log, 500)
        sig = fx.ssh_sign(cp, self.root, fx.NS_CHECKPOINT)
        keys = [self.root_pub]
        self.assertTrue(fx.verify_against_checkpoint("s1", log + self.log(7)[5:], cp, sig, keys))   # extension
        for bad in (self.log(3), self.log(5, "b")):                                              # rollback, fork
            with self.assertRaises(fx.SecurityError):
                fx.verify_against_checkpoint("s1", bad, cp, sig, keys)
        forged = fx.ssh_sign(cp, self.assistant, fx.NS_CHECKPOINT)
        with self.assertRaises(fx.SecurityError):
            fx.verify_against_checkpoint("s1", log, cp, forged, keys)
        with self.assertRaises(fx.SecurityError):
            fx.verify_against_checkpoint("other-log", log, cp, sig, keys)


class Legacy(unittest.TestCase):
    def test_exact_identity_only(self):
        m = fx.LegacyManifest([("E1", "c1", 3), ("E2", "c2", 2)])
        pin = m.digest
        self.assertTrue(m.exempt("E1", "c1", 3, pin))
        self.assertFalse(m.exempt("E1", "c9", 3, pin))       # reused id with another commit
        self.assertFalse(m.exempt("E1", "c1", 4, pin))       # another protocol
        self.assertFalse(m.exempt("E3", "c3", 3, pin))       # new experiment
        m2 = fx.LegacyManifest([("E1", "c1", 3), ("E2", "c2", 2), ("E3", "c3", 3)])   # smuggled in
        with self.assertRaises(fx.SecurityError):
            m2.exempt("E3", "c3", 3, pin)


class Data(unittest.TestCase):
    def setUp(self):
        self.content = b"open,high,low,close\n"
        self.lock = fx.data_lock({"BTC-1h-2022-01.zip": hashlib.sha256(self.content).hexdigest()},
                                 "https://data.binance.vision/...CHECKSUM", 100, 200)
        self.pin = fx.sha(self.lock)

    def test_valid_access_carries_the_limitation(self):
        self.assertEqual(fx.verify_access(self.lock, "BTC-1h-2022-01.zip", self.content, 300, self.pin),
                         ["CHECKSUM_SAME_SOURCE"])

    def test_attacks(self):
        with self.assertRaises(fx.SecurityError):
            fx.verify_access(self.lock, "BTC-1h-2022-01.zip", b"tampered", 300, self.pin)
        with self.assertRaises(fx.SecurityError):
            fx.verify_access(self.lock, "BTC-1h-2022-01.zip", self.content, 150, self.pin)      # before lock
        with self.assertRaises(fx.SecurityError):
            fx.verify_access(self.lock, "ETH-1h-2022-01.zip", self.content, 300, self.pin)      # not locked
        altered = dict(self.lock, lock_ts=50)
        with self.assertRaises(fx.SecurityError):
            fx.verify_access(altered, "BTC-1h-2022-01.zip", self.content, 300, self.pin)
        with self.assertRaises(fx.SecurityError):
            fx.data_lock({}, "src", 300, 200)                                                   # lock before fetch


class Universe(unittest.TestCase):
    D = 86400
    RULE = {"window_start": 1000 * 86400, "min_history_days": 30, "include_delisted": True}
    INDEX = {"BTC": [0, None], "LUNA": [500 * 86400, 1100 * 86400], "NEW": [990 * 86400, None],
             "OLD": [0, 900 * 86400]}

    def test_point_in_time_membership(self):
        self.assertEqual(fx.universe(self.RULE, self.INDEX), ["BTC", "LUNA"])   # delisted later: in; new/old: out
        with self.assertRaises(fx.SecurityError):
            fx.universe(dict(self.RULE, include_delisted=False), self.INDEX)

    def test_lock_and_attacks(self):
        lock = fx.universe_lock(self.RULE, self.INDEX, rule_ts=10, index_fetched_ts=20, lock_ts=30)
        self.assertEqual(fx.verify_universe(lock, self.RULE, self.INDEX), ["BTC", "LUNA"])
        with self.assertRaises(fx.SecurityError):                                   # index changed afterwards
            fx.verify_universe(lock, self.RULE, {k: v for k, v in self.INDEX.items() if k != "LUNA"})
        with self.assertRaises(fx.SecurityError):                                   # rule changed afterwards
            fx.verify_universe(lock, dict(self.RULE, min_history_days=10), self.INDEX)
        recon = fx.universe_lock(self.RULE, self.INDEX, rule_ts=10, index_fetched_ts=40, lock_ts=30)
        self.assertEqual(recon["status"], "RECONSTRUCTED")
        with self.assertRaises(fx.SecurityError):
            fx.verify_universe(recon, self.RULE, self.INDEX)
        with self.assertRaises(fx.SecurityError):                                   # rule after the index was seen
            fx.universe_lock(self.RULE, self.INDEX, rule_ts=25, index_fetched_ts=20, lock_ts=30)


class OwnerActions(unittest.TestCase):
    def test_listed_and_never_done_by_the_assistant(self):
        self.assertGreaterEqual(len(fx.OWNER_ACTIONS), 5)
        self.assertTrue(any("id_ed25519" in a for a in fx.OWNER_ACTIONS))


if __name__ == "__main__":
    unittest.main()
