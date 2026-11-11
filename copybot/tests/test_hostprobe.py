"""hostprobe on a synthetic /proc and /sys tree in a temporary directory; nothing on the host is read or changed."""
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "research", "ops", "hostprobe"))
import hostprobe as hp  # noqa: E402


def write(root, rel, text):
    p = os.path.join(root, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="ascii") as f:
        f.write(text)


class Probe(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = tmp.name
        write(self.root, "proc/stat", "cpu  100 0 100 700 100 0 0 0 0 0\ncpu0 1 2 3 4\n")
        write(self.root, "proc/loadavg", "1.24 1.39 1.17 3/812 99\n")
        write(self.root, "proc/meminfo", "MemTotal: 16268288 kB\nMemAvailable: 13312000 kB\nDirty: 2048 kB\n")
        write(self.root, "proc/pressure/cpu", "some avg10=1.50 avg60=0.00 avg300=0.00 total=1\n")
        write(self.root, "proc/pressure/io", "some avg10=0.20 avg60=0 avg300=0 total=1\nfull avg10=0.10 avg60=0 "
                                             "avg300=0 total=1\n")
        write(self.root, "proc/diskstats", "   8       0 sda 718983 13492 10804095 157731 1374126 615120 22833834 "
                                           "1490078 2 999 1650000 0 0 0 0\n")
        write(self.root, "sys/class/hwmon/hwmon1/name", "coretemp\n")
        write(self.root, "sys/class/hwmon/hwmon1/temp1_input", "45000\n")
        write(self.root, "sys/class/hwmon/hwmon1/temp1_label", "Package id 0\n")
        for c in ("cpu0", "cpu1"):
            write(self.root, f"sys/devices/system/cpu/{c}/thermal_throttle/core_throttle_count", "2\n")
        write(self.root, "proc/123/stat", "123 (python3) S 1 1 1 0 -1 0 0 0 0 0 500 100 0 0 20 0 1 0 1 1 2560 0\n")

    def test_one_sample_has_every_field(self):
        rec, cur = hp.sample(0, (900, 750), self.root, now=1794300000.0, ssd=lambda: 28.0)
        self.assertEqual(rec["load1"], 1.24)
        self.assertEqual(rec["procs_running"], 3)
        self.assertEqual(rec["mem"]["MemAvailable"], 13000)
        self.assertEqual(rec["psi"]["io_full10"], 0.1)
        self.assertEqual(rec["temp"]["coretemp:Package id 0"], 45.0)
        self.assertEqual(rec["throttle"]["core_throttle_count"], 4)
        self.assertEqual(rec["disk"]["in_flight"], 2)
        self.assertEqual(rec["top"][0]["name"], "python3")
        self.assertEqual(rec["ssd_c"], 28.0)
        self.assertEqual(cur, (1000, 800))
        self.assertEqual(rec["cpu_pct"], 50.0)

    def test_top_and_ssd_only_on_their_ticks(self):
        rec, _ = hp.sample(1, None, self.root, now=1.0, ssd=lambda: 1 / 0)
        self.assertNotIn("top", rec)
        self.assertNotIn("ssd_c", rec)
        self.assertIsNone(rec["cpu_pct"])

    def test_missing_files_do_not_crash(self):
        with tempfile.TemporaryDirectory() as empty:
            rec, _ = hp.sample(0, None, empty, now=1.0, ssd=lambda: None)
        self.assertIsNone(rec["load1"])
        self.assertEqual(rec["temp"], {})

    def test_append_writes_one_json_line_per_sample_by_utc_day(self):
        out = os.path.join(self.root, "out")
        p1 = hp.append(out, {"ts": 1794300000.0, "x": 1})
        hp.append(out, {"ts": 1794300010.0, "x": 2})
        with open(p1, encoding="utf-8") as f:
            lines = [json.loads(x) for x in f]
        self.assertEqual([x["x"] for x in lines], [1, 2])
        self.assertTrue(p1.endswith("2026-11-10.jsonl"))

    def test_no_network_or_database_in_the_source(self):
        with open(hp.__file__, encoding="utf-8") as f:
            src = f.read()
        for word in ("socket", "urllib", "http", "sqlite3", "lab.db"):
            self.assertNotIn(word, src)


if __name__ == "__main__":
    import direct_guard  # noqa: E402,F401  (order 75: quarantine guard for direct runs)
    unittest.main()
